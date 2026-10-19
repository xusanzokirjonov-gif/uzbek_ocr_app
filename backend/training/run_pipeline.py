#!/usr/bin/env python3
"""
Uzbek OCR Pipeline Runner
==========================
Unified script to run all or individual stages of the training pipeline.

Usage:
    python run_pipeline.py --steps all          # Full pipeline
    python run_pipeline.py --steps generate     # Only synthetic data generation
    python run_pipeline.py --steps lmdb         # Only LMDB conversion
    python run_pipeline.py --steps train        # Only training
    python run_pipeline.py --steps export       # Only export model for inference
    python run_pipeline.py --steps lmdb train   # LMDB + training

Each step can be run independently; the pipeline checks for required
inputs before starting each stage.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys

# Enable fallback to CPU for operators not implemented on MPS
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
from pathlib import Path

import torch
import yaml

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_pipeline")

# ---------------------------------------------------------------------------
# Paths (relative to this script)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
MODEL_DIR = BACKEND_DIR / "model"

PREPARE_LMDB_SCRIPT = SCRIPT_DIR / "prepare_lmdb.py"
TRAIN_SCRIPT = SCRIPT_DIR / "train_model.py"
CONFIG_PATH = SCRIPT_DIR / "uzbek_config.yaml"

# Possible location for a data-generation script (optional)
GENERATE_SCRIPT = SCRIPT_DIR / "generate_data.py"

# Where training saves checkpoints
SAVED_MODELS_DIR = SCRIPT_DIR / "saved_models"

# Target inference model path
INFERENCE_MODEL_PATH = MODEL_DIR / "uzbek_model.pth"

ALL_STEPS = ["generate", "lmdb", "train", "export"]


# ===================================================================
# Step implementations
# ===================================================================


def _run_subprocess(cmd: list[str], description: str) -> bool:
    """Run a subprocess and stream output. Returns True on success."""
    logger.info("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=str(SCRIPT_DIR),
            check=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("%s failed with exit code %d", description, exc.returncode)
        return False
    except FileNotFoundError:
        logger.error("Python executable or script not found: %s", cmd)
        return False


def step_generate(args: argparse.Namespace) -> bool:
    """
    Step: Generate synthetic training data.

    Calls generate_data.py if it exists. This step is optional — if
    you already have real data in data/raw/{train,val}/, skip this.
    """
    logger.info("=" * 60)
    logger.info("  STEP: generate — Synthetic Data Generation")
    logger.info("=" * 60)

    if not GENERATE_SCRIPT.exists():
        logger.warning(
            "generate_data.py not found at %s. "
            "Skipping generation — ensure you have data in data/raw/.",
            GENERATE_SCRIPT,
        )
        return True  # Non-fatal: user may have real data

    cmd = [sys.executable, str(GENERATE_SCRIPT)]
    if hasattr(args, "num_samples") and args.num_samples is not None:
        cmd.extend(["--count", str(args.num_samples)])
        # Set validation count to 20% of training count
        val_count = max(1, int(args.num_samples * 0.2))
        cmd.extend(["--val-count", str(val_count)])

    return _run_subprocess(cmd, "Data generation")


def step_lmdb(args: argparse.Namespace) -> bool:
    """
    Step: Convert raw data to LMDB format.

    Requires: data/raw/train/gt.txt and data/raw/val/gt.txt
    Produces: data/train_lmdb/ and data/val_lmdb/
    """
    logger.info("=" * 60)
    logger.info("  STEP: lmdb — LMDB Preparation")
    logger.info("=" * 60)

    # Check prerequisites
    train_gt = DATA_DIR / "raw" / "train" / "gt.txt"
    val_gt = DATA_DIR / "raw" / "val" / "gt.txt"

    if not train_gt.exists():
        logger.error(
            "Training ground-truth file not found: %s\n"
            "Run the 'generate' step first, or place your data manually.",
            train_gt,
        )
        return False

    if not val_gt.exists():
        logger.warning("Validation gt.txt not found: %s (will skip val split)", val_gt)

    cmd = [sys.executable, str(PREPARE_LMDB_SCRIPT)]
    return _run_subprocess(cmd, "LMDB preparation")


def step_train(args: argparse.Namespace) -> bool:
    """
    Step: Train the CRNN model.

    Requires: data/train_lmdb/ and data/val_lmdb/
    Produces: saved_models/<experiment_name>/best_accuracy.pth
    """
    logger.info("=" * 60)
    logger.info("  STEP: train — Model Training")
    logger.info("=" * 60)

    # Check prerequisites
    train_lmdb = DATA_DIR / "train_lmdb"
    val_lmdb = DATA_DIR / "val_lmdb"

    if not train_lmdb.exists():
        logger.error(
            "Training LMDB not found: %s\n"
            "Run the 'lmdb' step first.",
            train_lmdb,
        )
        return False

    if not val_lmdb.exists():
        logger.error(
            "Validation LMDB not found: %s\n"
            "Run the 'lmdb' step first.",
            val_lmdb,
        )
        return False

    cmd = [sys.executable, str(TRAIN_SCRIPT), "--config", str(CONFIG_PATH)]

    if args.device:
        cmd.extend(["--device", args.device])
    if args.batch_size:
        cmd.extend(["--batch_size", str(args.batch_size)])
    if args.num_iter:
        cmd.extend(["--num_iter", str(args.num_iter)])
    if args.resume:
        cmd.append("--resume")

    return _run_subprocess(cmd, "Model training")


def step_export(args: argparse.Namespace) -> bool:
    """
    Step: Export the best trained model for inference.

    Copies best_accuracy.pth -> model/uzbek_model.pth and verifies
    the model loads correctly.
    """
    logger.info("=" * 60)
    logger.info("  STEP: export — Model Export for Inference")
    logger.info("=" * 60)

    # Load config to get experiment name
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        experiment_name = cfg.get("experiment_name", "uzbek_ocr")
    else:
        experiment_name = "uzbek_ocr"

    best_model_path = SAVED_MODELS_DIR / experiment_name / "best_accuracy.pth"

    if not best_model_path.exists():
        latest_path = SAVED_MODELS_DIR / experiment_name / "latest.pth"
        if latest_path.exists():
            logger.info("best_accuracy.pth not found. Using latest.pth as fallback.")
            best_model_path = latest_path
        else:
            logger.error(
                "No checkpoints (best_accuracy.pth or latest.pth) found at %s\n"
                "Run the 'train' step first.",
                SAVED_MODELS_DIR / experiment_name,
            )
            return False

    # Ensure model directory exists
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Extract model_state_dict and format for EasyOCR
    logger.info("Extracting model_state_dict from %s and saving to %s", best_model_path, INFERENCE_MODEL_PATH)
    try:
        checkpoint = torch.load(
            str(best_model_path), map_location="cpu", weights_only=False
        )

        if "model_state_dict" not in checkpoint:
            logger.error("Checkpoint is missing 'model_state_dict' key!")
            return False

        state_dict = checkpoint["model_state_dict"]

        # EasyOCR expects all keys to be prefixed with 'module.'
        from collections import OrderedDict
        new_state_dict = OrderedDict()
        for k, v in state_dict.items():
            if not k.startswith("module."):
                new_key = "module." + k
            else:
                new_key = k
            new_state_dict[new_key] = v

        torch.save(new_state_dict, str(INFERENCE_MODEL_PATH))

        # Verify the model loads correctly
        logger.info("Verifying exported model ...")
        loaded_state_dict = torch.load(
            str(INFERENCE_MODEL_PATH), map_location="cpu", weights_only=False
        )

        if not isinstance(loaded_state_dict, dict):
            logger.error("Exported file is not a dictionary!")
            return False

        num_params = sum(
            v.numel() for v in loaded_state_dict.values() if isinstance(v, torch.Tensor)
        )

        accuracy = checkpoint.get("best_accuracy", checkpoint.get("accuracy", "N/A"))
        iteration = checkpoint.get("iteration", "N/A")
        charset = checkpoint.get("charset", "")

        logger.info("=" * 50)
        logger.info("  ✅ Model Export Summary")
        logger.info("  -" * 25)
        logger.info("  Path:       %s", INFERENCE_MODEL_PATH)
        logger.info("  Parameters: %s", f"{num_params:,}")
        logger.info("  Accuracy:   %s", accuracy)
        logger.info("  Iteration:  %s", iteration)
        logger.info("  Charset:    %d characters", len(charset))
        logger.info(
            "  File size:  %.2f MB",
            INFERENCE_MODEL_PATH.stat().st_size / (1024 * 1024),
        )
        logger.info("=" * 50)

        return True

    except Exception as exc:
        logger.error("Failed to export or verify model: %s", exc)
        return False


# ===================================================================
# CLI
# ===================================================================


STEP_FUNCTIONS = {
    "generate": step_generate,
    "lmdb": step_lmdb,
    "train": step_train,
    "export": step_export,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Uzbek OCR training pipeline (all or individual steps).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Steps:
  generate   Generate synthetic training data (optional)
  lmdb       Convert raw data to LMDB format
  train      Train the CRNN model
  export     Export best model for EasyOCR inference
  all        Run all steps in order
        """,
    )
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=ALL_STEPS + ["all"],
        default=["all"],
        help="Which pipeline steps to run (default: all)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["auto", "cpu", "mps", "cuda"],
        help="Compute device for training (default: auto-detect)",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=None,
        help="Override batch size for training",
    )
    parser.add_argument(
        "--num_iter",
        type=int,
        default=None,
        help="Override number of training iterations",
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        default=None,
        help="Number of samples for data generation",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume training from latest checkpoint",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve step list
    if "all" in args.steps:
        steps = ALL_STEPS
    else:
        # Preserve user-specified order, deduplicate
        seen: set[str] = set()
        steps: list[str] = []
        for s in args.steps:
            if s not in seen:
                seen.add(s)
                steps.append(s)

    logger.info("🚀 Uzbek OCR Pipeline")
    logger.info("   Steps: %s", " → ".join(steps))
    logger.info("")

    for step_name in steps:
        fn = STEP_FUNCTIONS[step_name]
        ok = fn(args)
        if not ok:
            logger.error("❌ Pipeline aborted at step '%s'", step_name)
            sys.exit(1)
        logger.info("✅ Step '%s' completed successfully.\n", step_name)

    logger.info("🎉 Pipeline finished successfully!")


if __name__ == "__main__":
    main()
