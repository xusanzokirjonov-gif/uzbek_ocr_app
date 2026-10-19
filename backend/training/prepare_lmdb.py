#!/usr/bin/env python3
"""
LMDB Dataset Preparation
=========================
Converts raw image + label data (gt.txt format) into LMDB databases
for efficient training data loading.

Usage:
    python prepare_lmdb.py                          # Convert train + val
    python prepare_lmdb.py --verify                 # Verify existing LMDB
    python prepare_lmdb.py --splits train           # Only convert train
    python prepare_lmdb.py --splits val             # Only convert val
    python prepare_lmdb.py --map-size 2             # Set map size in GB

gt.txt format (tab-separated):
    image_filename<TAB>label_text
    img_00001.png<TAB>Salom dunyo
"""

from __future__ import annotations

import argparse
import logging
import os
import struct
import sys
from pathlib import Path
from typing import Optional

import lmdb
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("prepare_lmdb")

# ---------------------------------------------------------------------------
# Paths (relative to this script)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data"

SPLIT_CONFIG = {
    "train": {
        "raw_dir": DATA_DIR / "raw" / "train",
        "lmdb_dir": DATA_DIR / "train_lmdb",
    },
    "val": {
        "raw_dir": DATA_DIR / "raw" / "val",
        "lmdb_dir": DATA_DIR / "val_lmdb",
    },
}


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _read_gt_file(gt_path: Path) -> list[tuple[str, str]]:
    """
    Read a ground-truth file and return a list of (image_filename, label) tuples.

    The file should be tab-separated:
        image_filename\\tlabel_text
    """
    entries: list[tuple[str, str]] = []
    with open(gt_path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue

            # Support both tab and first-space separation
            if "\t" in line:
                parts = line.split("\t", maxsplit=1)
            else:
                parts = line.split(" ", maxsplit=1)

            if len(parts) != 2:
                logger.warning(
                    "Skipping malformed line %d in %s: %r", line_no, gt_path, line
                )
                continue

            img_name, label = parts[0].strip(), parts[1].strip()
            if not img_name or not label:
                logger.warning(
                    "Empty image name or label at line %d in %s", line_no, gt_path
                )
                continue

            entries.append((img_name, label))

    return entries


def _create_lmdb(
    raw_dir: Path,
    lmdb_dir: Path,
    map_size_gb: float = 10.0,
) -> int:
    """
    Create an LMDB database from raw images + gt.txt.

    LMDB key scheme:
        image-000000001  ->  raw image bytes
        label-000000001  ->  UTF-8 encoded label string
        num-samples      ->  total number of samples (ASCII int)

    Returns the number of samples written.
    """
    gt_path = raw_dir / "gt.txt"
    if not gt_path.exists():
        logger.error("Ground-truth file not found: %s", gt_path)
        return 0

    entries = _read_gt_file(gt_path)
    if not entries:
        logger.error("No valid entries found in %s", gt_path)
        return 0

    logger.info(
        "Found %d entries in %s, writing to %s ...",
        len(entries),
        gt_path,
        lmdb_dir,
    )

    # Ensure output directory exists
    lmdb_dir.mkdir(parents=True, exist_ok=True)

    map_size = int(map_size_gb * 1024 * 1024 * 1024)  # GB -> bytes
    env = lmdb.open(str(lmdb_dir), map_size=map_size)

    written = 0
    skipped = 0

    with env.begin(write=True) as txn:
        for idx, (img_name, label) in enumerate(
            tqdm(entries, desc=f"  Writing {raw_dir.name}", unit="img"),
            start=1,
        ):
            img_path = raw_dir / img_name
            if not img_path.exists():
                img_path = raw_dir / "images" / img_name
            if not img_path.exists():
                logger.warning("Image not found, skipping: %s", img_path)
                skipped += 1
                continue

            with open(img_path, "rb") as img_fh:
                img_bytes = img_fh.read()

            if len(img_bytes) == 0:
                logger.warning("Empty image file, skipping: %s", img_path)
                skipped += 1
                continue

            # Store with 9-digit zero-padded index
            image_key = f"image-{idx:09d}".encode("utf-8")
            label_key = f"label-{idx:09d}".encode("utf-8")

            txn.put(image_key, img_bytes)
            txn.put(label_key, label.encode("utf-8"))
            written += 1

        # Write total sample count
        txn.put("num-samples".encode("utf-8"), str(written).encode("utf-8"))

    env.close()

    logger.info(
        "✅  LMDB created: %d samples written, %d skipped -> %s",
        written,
        skipped,
        lmdb_dir,
    )
    return written


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _verify_lmdb(lmdb_dir: Path) -> bool:
    """
    Open an LMDB and verify its integrity:
    - num-samples key exists and is a valid int
    - Each image-NNNNNNNNN and label-NNNNNNNNN key exists
    - Image bytes are non-empty
    - Label strings are non-empty
    """
    if not lmdb_dir.exists():
        logger.error("LMDB directory does not exist: %s", lmdb_dir)
        return False

    env = lmdb.open(str(lmdb_dir), readonly=True, lock=False)
    ok = True

    with env.begin(write=False) as txn:
        # Check num-samples
        raw = txn.get("num-samples".encode("utf-8"))
        if raw is None:
            logger.error("Missing 'num-samples' key in %s", lmdb_dir)
            env.close()
            return False

        try:
            num_samples = int(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            logger.error(
                "Invalid 'num-samples' value in %s: %s", lmdb_dir, exc
            )
            env.close()
            return False

        logger.info("Verifying %d samples in %s ...", num_samples, lmdb_dir)

        errors = 0
        for idx in tqdm(range(1, num_samples + 1), desc="  Verifying", unit="img"):
            image_key = f"image-{idx:09d}".encode("utf-8")
            label_key = f"label-{idx:09d}".encode("utf-8")

            img_data = txn.get(image_key)
            lbl_data = txn.get(label_key)

            if img_data is None:
                logger.error("Missing image key: image-%09d", idx)
                errors += 1
                continue

            if lbl_data is None:
                logger.error("Missing label key: label-%09d", idx)
                errors += 1
                continue

            if len(img_data) == 0:
                logger.error("Empty image bytes for index %d", idx)
                errors += 1

            label_str = lbl_data.decode("utf-8")
            if not label_str:
                logger.error("Empty label string for index %d", idx)
                errors += 1

        if errors > 0:
            logger.error(
                "❌  Verification FAILED: %d errors in %s", errors, lmdb_dir
            )
            ok = False
        else:
            logger.info("✅  Verification PASSED: %d samples OK in %s", num_samples, lmdb_dir)

    env.close()
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare LMDB datasets for Uzbek OCR training.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=["train", "val"],
        default=["train", "val"],
        help="Which splits to process (default: train val)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing LMDB databases instead of creating them",
    )
    parser.add_argument(
        "--map-size",
        type=float,
        default=10.0,
        help="LMDB map size in GB (default: 10.0)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Override base data directory (default: <backend>/data)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Allow overriding the data directory
    if args.data_dir:
        base = Path(args.data_dir).resolve()
        split_config = {
            "train": {
                "raw_dir": base / "raw" / "train",
                "lmdb_dir": base / "train_lmdb",
            },
            "val": {
                "raw_dir": base / "raw" / "val",
                "lmdb_dir": base / "val_lmdb",
            },
        }
    else:
        split_config = SPLIT_CONFIG

    if args.verify:
        logger.info("=== LMDB Verification Mode ===")
        all_ok = True
        for split in args.splits:
            cfg = split_config[split]
            if not _verify_lmdb(cfg["lmdb_dir"]):
                all_ok = False
        if not all_ok:
            sys.exit(1)
        logger.info("All verifications passed.")
        return

    logger.info("=== LMDB Preparation ===")
    total = 0
    for split in args.splits:
        cfg = split_config[split]
        raw_dir = cfg["raw_dir"]
        lmdb_dir = cfg["lmdb_dir"]

        if not raw_dir.exists():
            logger.warning(
                "Raw data directory does not exist, skipping split '%s': %s",
                split,
                raw_dir,
            )
            continue

        count = _create_lmdb(raw_dir, lmdb_dir, map_size_gb=args.map_size)
        total += count

    logger.info("=== Done: %d total samples across all splits ===", total)


if __name__ == "__main__":
    main()
