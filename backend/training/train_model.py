#!/usr/bin/env python3
"""
Uzbek OCR Training Script
==========================
Standalone CRNN (VGG + BiLSTM + CTC) trainer for Uzbek text recognition.

Does NOT depend on EasyOCR's trainer or deep-text-recognition-benchmark.
Everything is implemented internally.

Supports: CPU, CUDA, and Apple Silicon MPS (auto-detected).

Usage:
    python train_model.py                                 # defaults
    python train_model.py --config uzbek_config.yaml      # explicit config
    python train_model.py --device mps --batch_size 32    # override
    python train_model.py --resume                        # resume training
"""

from __future__ import annotations

import os
# Enable fallback to CPU for operators not implemented on MPS (like CTC loss)
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import argparse
import io
import logging
import random
import sys
import time
from pathlib import Path
from typing import Optional

import lmdb
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("train_model")

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


# ===================================================================
# MODEL ARCHITECTURE
# ===================================================================


class VGG_FeatureExtractor(nn.Module):
    """
    VGG-like CNN for feature extraction.

    Input:  (batch, 1, 64, W) grayscale images
    Output: (batch, 256, 1, W//4) feature maps
    """

    def __init__(self, input_channel: int = 1, output_channel: int = 256) -> None:
        super().__init__()
        self.output_channel = [
            int(output_channel / 8),   # 32
            int(output_channel / 4),   # 64
            int(output_channel / 2),   # 128
            output_channel,            # 256
        ]

        self.conv_net = nn.Sequential(
            # Block 1: input_channel -> 32
            nn.Conv2d(input_channel, self.output_channel[0], 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d(2, 2),  # 64 -> 32

            # Block 2: 32 -> 64
            nn.Conv2d(self.output_channel[0], self.output_channel[1], 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d(2, 2),  # 32 -> 16

            # Block 3: 64 -> 128 (two conv layers)
            nn.Conv2d(self.output_channel[1], self.output_channel[2], 3, 1, 1),
            nn.ReLU(True),
            nn.Conv2d(self.output_channel[2], self.output_channel[2], 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d((2, 1), (2, 1)),  # 16 -> 8 (height only)

            # Block 4: 128 -> 256 (two conv layers + BN)
            nn.Conv2d(self.output_channel[2], self.output_channel[3], 3, 1, 1, bias=False),
            nn.BatchNorm2d(self.output_channel[3]),
            nn.ReLU(True),
            nn.Conv2d(self.output_channel[3], self.output_channel[3], 3, 1, 1, bias=False),
            nn.BatchNorm2d(self.output_channel[3]),
            nn.ReLU(True),
            nn.MaxPool2d((2, 1), (2, 1)),  # 8 -> 4

            # Final squeeze: 4 -> 1 (height)
            nn.Conv2d(self.output_channel[3], self.output_channel[3], 2, (2, 1), (0, 1)),
            nn.ReLU(True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv_net(x)


class BidirectionalLSTM(nn.Module):
    """
    BiLSTM for sequence modelling.

    Input:  (seq_len, batch, input_size)
    Output: (seq_len, batch, output_size)
    """

    def __init__(self, input_size: int, hidden_size: int, output_size: int) -> None:
        super().__init__()
        self.rnn = nn.LSTM(input_size, hidden_size, bidirectional=True, batch_first=False)
        self.linear = nn.Linear(hidden_size * 2, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        recurrent, _ = self.rnn(x)  # (seq, batch, hidden*2)
        output = self.linear(recurrent)  # (seq, batch, output_size)
        return output


class CRNN(nn.Module):
    """
    Full CRNN model: VGG → reshape → BiLSTM × 2 → Linear → logits.

    Returns logits of shape (seq_len, batch, num_classes).
    """

    def __init__(
        self,
        input_channel: int = 1,
        output_channel: int = 256,
        hidden_size: int = 256,
        num_class: int = 100,
    ) -> None:
        super().__init__()
        self.feature_extractor = VGG_FeatureExtractor(input_channel, output_channel)
        self.adaptive_pool = nn.AdaptiveAvgPool2d((1, None))  # squeeze height to 1

        self.sequence_model = nn.Sequential(
            BidirectionalLSTM(output_channel, hidden_size, hidden_size),
            BidirectionalLSTM(hidden_size, hidden_size, hidden_size),
        )
        self.prediction = nn.Linear(hidden_size, num_class)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, C, H, W)
        visual = self.feature_extractor(x)  # (batch, output_channel, H', W')
        visual = self.adaptive_pool(visual)  # (batch, output_channel, 1, W')

        # Squeeze height dimension, permute to (batch, W', C)
        visual = visual.squeeze(2)  # (batch, C, W')
        visual = visual.permute(2, 0, 1)  # (W', batch, C) = (seq, batch, feat)

        contextual = self.sequence_model(visual)  # (seq, batch, hidden)
        output = self.prediction(contextual)  # (seq, batch, num_class)
        return output


# ===================================================================
# DATASET
# ===================================================================


class LMDBDataset(Dataset):
    """
    Reads image-label pairs from an LMDB database.

    Expected LMDB keys:
        num-samples          -> total count
        image-000000001 ...  -> raw image bytes
        label-000000001 ...  -> UTF-8 label string
    """

    def __init__(
        self,
        lmdb_path: str | Path,
        img_h: int = 64,
        img_w: int = 600,
        rgb: bool = False,
        max_label_length: int = 40,
        charset: str = "",
        data_filtering_off: bool = False,
    ) -> None:
        self.lmdb_path = str(lmdb_path)
        self.img_h = img_h
        self.img_w = img_w
        self.rgb = rgb
        self.max_label_length = max_label_length
        self.charset = set(charset)
        self.data_filtering_off = data_filtering_off

        # Open LMDB environment temporarily to count samples and build index
        temp_env = lmdb.open(
            self.lmdb_path,
            max_readers=32,
            readonly=True,
            lock=False,
            readahead=False,
            meminit=False,
        )
        with temp_env.begin(write=False) as txn:
            raw = txn.get("num-samples".encode("utf-8"))
            if raw is None:
                raise ValueError(f"LMDB at {lmdb_path} is missing 'num-samples' key.")
            self.num_samples = int(raw.decode("utf-8"))

        # Build filtered index (skip samples that don't match charset / length)
        self.filtered_indices: list[int] = []
        self._build_index(temp_env)
        temp_env.close()

        # Set environment to None for pickling compatibility
        self.env = None

    def _build_index(self, env: lmdb.Environment) -> None:
        """Pre-scan labels to filter out samples with unsupported chars."""
        with env.begin(write=False) as txn:
            for idx in range(1, self.num_samples + 1):
                label_key = f"label-{idx:09d}".encode("utf-8")
                raw = txn.get(label_key)
                if raw is None:
                    continue
                label = raw.decode("utf-8")

                # Length filter
                if len(label) > self.max_label_length:
                    continue

                # Character filter
                if not self.data_filtering_off and self.charset:
                    if any(c not in self.charset for c in label):
                        continue

                self.filtered_indices.append(idx)

        logger.info(
            "LMDBDataset(%s): %d / %d samples after filtering",
            self.lmdb_path,
            len(self.filtered_indices),
            self.num_samples,
        )

    def __len__(self) -> int:
        return len(self.filtered_indices)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, str]:
        real_idx = self.filtered_indices[index]

        if self.env is None:
            self.env = lmdb.open(
                self.lmdb_path,
                max_readers=32,
                readonly=True,
                lock=False,
                readahead=False,
                meminit=False,
            )

        with self.env.begin(write=False) as txn:
            image_key = f"image-{real_idx:09d}".encode("utf-8")
            label_key = f"label-{real_idx:09d}".encode("utf-8")

            img_bytes = txn.get(image_key)
            label = txn.get(label_key).decode("utf-8")  # type: ignore[union-attr]

        # Decode image
        buf = io.BytesIO(img_bytes)  # type: ignore[arg-type]
        pil_img = Image.open(buf)

        if self.rgb:
            pil_img = pil_img.convert("RGB")
        else:
            pil_img = pil_img.convert("L")

        # Resize to target height, keeping aspect ratio, then pad/crop to width
        w, h = pil_img.size
        ratio = self.img_h / h
        new_w = min(int(w * ratio), self.img_w)
        pil_img = pil_img.resize((new_w, self.img_h), Image.BILINEAR)

        # Convert to tensor (0-1 float)
        img_array = np.array(pil_img, dtype=np.float32)
        if len(img_array.shape) == 2:
            img_array = np.expand_dims(img_array, axis=0)  # (1, H, W)
        else:
            img_array = img_array.transpose(2, 0, 1)  # (C, H, W)
        img_tensor = torch.from_numpy(img_array) / 255.0

        # Pad width to img_w using the background pixel value (from top-right corner)
        c, th, tw = img_tensor.shape
        if tw < self.img_w:
            bg_val = img_tensor[0, 0, tw - 1].item()
            pad = torch.full((c, th, self.img_w - tw), bg_val)
            img_tensor = torch.cat([img_tensor, pad], dim=2)
        elif tw > self.img_w:
            img_tensor = img_tensor[:, :, : self.img_w]

        return img_tensor, label


class AlignCollate:
    """
    Custom collate that ensures all images in a batch have the same dimensions.
    Returns (batch_images, list_of_label_strings).
    """

    def __init__(self, img_h: int = 64, img_w: int = 600, pad: bool = True) -> None:
        self.img_h = img_h
        self.img_w = img_w
        self.pad = pad

    def __call__(
        self, batch: list[tuple[torch.Tensor, str]]
    ) -> tuple[torch.Tensor, list[str]]:
        images, labels = zip(*batch)
        image_tensors = torch.stack(images, 0)  # (B, C, H, W)
        return image_tensors, list(labels)


# ===================================================================
# CTC LABEL ENCODING / DECODING
# ===================================================================


class CTCLabelConverter:
    """
    Convert between string labels and integer sequences for CTC.

    Index 0 is reserved for the CTC blank token.
    Characters are mapped 1 … N.
    """

    def __init__(self, character: str) -> None:
        # Remove duplicates while preserving order
        seen: set[str] = set()
        chars: list[str] = []
        for c in character:
            if c not in seen:
                seen.add(c)
                chars.append(c)

        self.character = ["[CTCblank]"] + chars
        self.num_classes = len(self.character)

        self.char2idx: dict[str, int] = {}
        for i, ch in enumerate(self.character):
            self.char2idx[ch] = i

    def encode(
        self, texts: list[str], batch_max_length: int = 40
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Encode a batch of label strings into padded integer tensors.

        Returns:
            targets: (batch, batch_max_length) — padded label indices
            lengths: (batch,) — true length of each label
        """
        lengths = [len(t) for t in texts]
        batch_size = len(texts)
        targets = torch.zeros(batch_size, batch_max_length, dtype=torch.long)

        for i, text in enumerate(texts):
            for j, ch in enumerate(text):
                if j >= batch_max_length:
                    break
                targets[i, j] = self.char2idx.get(ch, 0)

        return targets, torch.IntTensor(lengths)

    def decode(self, preds: torch.Tensor, lengths: torch.Tensor) -> list[str]:
        """
        Greedy CTC decoding.

        Args:
            preds: (batch, seq_len) — predicted class indices
            lengths: (batch,) — unused for greedy, kept for API compat

        Returns:
            list of decoded strings
        """
        results: list[str] = []
        for i in range(preds.size(0)):
            pred = preds[i]
            chars: list[str] = []
            prev = -1
            for idx in pred:
                idx_val = idx.item()
                if idx_val != 0 and idx_val != prev:
                    if idx_val < len(self.character):
                        chars.append(self.character[idx_val])
                prev = idx_val
            results.append("".join(chars))
        return results


# ===================================================================
# DEVICE SELECTION
# ===================================================================


def select_device(requested: str = "auto") -> torch.device:
    """
    Select the best available compute device.

    Priority: requested > MPS (Apple Silicon) > CUDA > CPU.
    """
    if requested == "auto":
        if torch.backends.mps.is_available():
            device = torch.device("mps")
            logger.info("🍎 Using Apple Silicon MPS acceleration")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
            logger.info("🟢 Using CUDA GPU: %s", torch.cuda.get_device_name(0))
        else:
            device = torch.device("cpu")
            logger.info("🔵 Using CPU")
    elif requested == "mps":
        if not torch.backends.mps.is_available():
            logger.warning("MPS requested but not available, falling back to CPU")
            device = torch.device("cpu")
        else:
            device = torch.device("mps")
            logger.info("🍎 Using Apple Silicon MPS acceleration")
    elif requested == "cuda":
        if not torch.cuda.is_available():
            logger.warning("CUDA requested but not available, falling back to CPU")
            device = torch.device("cpu")
        else:
            device = torch.device("cuda")
            logger.info("🟢 Using CUDA GPU: %s", torch.cuda.get_device_name(0))
    else:
        device = torch.device("cpu")
        logger.info("🔵 Using CPU")

    return device


# ===================================================================
# CONFIG LOADING
# ===================================================================


def load_config(config_path: str | Path) -> dict:
    """Load YAML config and return a dict."""
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg


def build_charset(cfg: dict) -> str:
    """
    Build the full character string from config fields:
    number + symbol + lang_char (deduplicated, order preserved).
    """
    raw = cfg.get("number", "") + cfg.get("symbol", "") + cfg.get("lang_char", "")
    seen: set[str] = set()
    chars: list[str] = []
    for c in raw:
        if c not in seen:
            seen.add(c)
            chars.append(c)
    return "".join(chars)


# ===================================================================
# VALIDATION
# ===================================================================


@torch.no_grad()
def validate(
    model: nn.Module,
    dataloader: DataLoader,
    converter: CTCLabelConverter,
    device: torch.device,
    batch_max_length: int = 40,
) -> tuple[float, int, int]:
    """
    Run validation and return (accuracy, num_correct, num_total).
    """
    model.eval()
    correct = 0
    total = 0

    for images, labels in dataloader:
        images = images.to(device)
        batch_size = images.size(0)

        preds = model(images)  # (seq, batch, num_class)
        pred_sizes = torch.IntTensor([preds.size(0)] * batch_size)
        _, pred_indices = preds.max(2)  # (seq, batch)
        pred_indices = pred_indices.transpose(1, 0).contiguous()  # (batch, seq)

        pred_strs = converter.decode(pred_indices, pred_sizes)

        for pred_str, gt_str in zip(pred_strs, labels):
            if pred_str == gt_str:
                correct += 1
            total += 1

    accuracy = correct / total if total > 0 else 0.0
    model.train()
    return accuracy, correct, total


# ===================================================================
# TRAINING
# ===================================================================


def train(args: argparse.Namespace) -> None:
    """Main training loop."""

    # ---------------------------------------------------------------
    # 1. Load config
    # ---------------------------------------------------------------
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = SCRIPT_DIR / config_path
    cfg = load_config(config_path)

    # CLI overrides
    num_iter: int = args.num_iter or cfg.get("num_iter", 10000)
    batch_size: int = args.batch_size or cfg.get("batch_size", 16)
    val_interval: int = cfg.get("valInterval", 500)
    img_h: int = cfg.get("imgH", 64)
    img_w: int = cfg.get("imgW", 600)
    rgb: bool = cfg.get("rgb", False)
    batch_max_length: int = cfg.get("batch_max_length", 40)
    grad_clip: float = cfg.get("grad_clip", 5.0)
    workers: int = cfg.get("workers", 4)
    seed: int = cfg.get("manualSeed", 1111)
    lr: float = cfg.get("lr", 1.0)
    data_filtering_off: bool = cfg.get("data_filtering_off", False)
    pad: bool = cfg.get("PAD", True)

    # ---------------------------------------------------------------
    # 2. Seed & device
    # ---------------------------------------------------------------
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    device = select_device(args.device)

    # ---------------------------------------------------------------
    # 3. Build character set & converter
    # ---------------------------------------------------------------
    charset = build_charset(cfg)
    converter = CTCLabelConverter(charset)
    num_class = converter.num_classes
    logger.info("Character set size: %d (+ CTC blank = %d classes)", len(charset), num_class)

    # ---------------------------------------------------------------
    # 4. Datasets & dataloaders
    # ---------------------------------------------------------------
    train_lmdb = args.train_data or (DATA_DIR / "train_lmdb")
    val_lmdb = args.val_data or (DATA_DIR / "val_lmdb")

    train_dataset = LMDBDataset(
        train_lmdb,
        img_h=img_h,
        img_w=img_w,
        rgb=rgb,
        max_label_length=batch_max_length,
        charset=charset,
        data_filtering_off=data_filtering_off,
    )
    val_dataset = LMDBDataset(
        val_lmdb,
        img_h=img_h,
        img_w=img_w,
        rgb=rgb,
        max_label_length=batch_max_length,
        charset=charset,
        data_filtering_off=data_filtering_off,
    )

    collate = AlignCollate(img_h=img_h, img_w=img_w, pad=pad)
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=workers,
        collate_fn=collate,
        pin_memory=True,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
        collate_fn=collate,
        pin_memory=True,
    )

    logger.info("Train samples: %d  |  Val samples: %d", len(train_dataset), len(val_dataset))

    # ---------------------------------------------------------------
    # 5. Model
    # ---------------------------------------------------------------
    input_channel = cfg.get("input_channel", 1)
    output_channel = cfg.get("output_channel", 256)
    hidden_size = cfg.get("hidden_size", 256)

    model = CRNN(
        input_channel=input_channel,
        output_channel=output_channel,
        hidden_size=hidden_size,
        num_class=num_class,
    )
    model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model params: %s total, %s trainable", f"{total_params:,}", f"{trainable_params:,}")

    # ---------------------------------------------------------------
    # 6. Loss, optimizer, scheduler
    # ---------------------------------------------------------------
    criterion = nn.CTCLoss(blank=0, zero_infinity=True)

    # Use Adadelta (the EasyOCR/DTRB default) or Adam
    use_adadelta: bool = cfg.get("optim", False)
    if use_adadelta:
        optimizer = optim.Adadelta(
            model.parameters(),
            lr=lr,
            rho=cfg.get("rho", 0.95),
            eps=cfg.get("eps", 1e-8),
        )
        logger.info("Optimizer: Adadelta (lr=%.4f)", lr)
    else:
        optimizer = optim.Adam(
            model.parameters(),
            lr=lr * 0.001,  # Adam typically needs smaller lr
            betas=(cfg.get("beta1", 0.9), 0.999),
        )
        logger.info("Optimizer: Adam (lr=%.6f)", lr * 0.001)

    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_iter)

    # ---------------------------------------------------------------
    # 7. Resume from checkpoint
    # ---------------------------------------------------------------
    save_dir = SCRIPT_DIR / "saved_models" / cfg.get("experiment_name", "uzbek_ocr")
    save_dir.mkdir(parents=True, exist_ok=True)

    start_iter = 0
    best_accuracy = 0.0

    latest_path = save_dir / "latest.pth"
    if args.resume and latest_path.exists():
        logger.info("Resuming from checkpoint: %s", latest_path)
        checkpoint = torch.load(latest_path, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        start_iter = checkpoint.get("iteration", 0)
        best_accuracy = checkpoint.get("best_accuracy", 0.0)
        logger.info(
            "Resumed at iteration %d (best_accuracy=%.4f)", start_iter, best_accuracy
        )

    # ---------------------------------------------------------------
    # 8. Training loop
    # ---------------------------------------------------------------
    model.train()
    train_iter = iter(train_loader)

    logger.info("=" * 60)
    logger.info("  Starting training: %d iterations", num_iter)
    logger.info("  Batch size: %d  |  Device: %s", batch_size, device)
    logger.info("  Validate every %d iters  |  Save to: %s", val_interval, save_dir)
    logger.info("=" * 60)

    loss_avg = 0.0
    loss_count = 0
    t0 = time.time()

    for iteration in range(start_iter + 1, num_iter + 1):
        # Get next batch (cycle through dataset)
        try:
            images, labels = next(train_iter)
        except StopIteration:
            train_iter = iter(train_loader)
            images, labels = next(train_iter)

        images = images.to(device)
        batch_size_actual = images.size(0)

        # Encode labels for CTC
        targets, target_lengths = converter.encode(labels, batch_max_length)
        targets = targets.to(device)

        # Forward
        preds = model(images)  # (seq_len, batch, num_class)
        pred_sizes = torch.IntTensor([preds.size(0)] * batch_size_actual)

        # CTC loss expects log-softmax input
        log_probs = F.log_softmax(preds, dim=2)  # (seq, batch, num_class)

        # CTC loss: (T, N, C), targets, input_lengths, target_lengths
        # Targets need to be concatenated (not padded) for CTC, or use the
        # padded version with target_lengths — PyTorch supports both.
        loss = criterion(log_probs, targets, pred_sizes, target_lengths)

        # Backward
        optimizer.zero_grad()
        loss.backward()
        if grad_clip > 0:
            nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()
        scheduler.step()

        loss_val = loss.item()
        loss_avg += loss_val
        loss_count += 1

        # ---------------------------------------------------------------
        # Logging
        # ---------------------------------------------------------------
        if iteration % 100 == 0 or iteration == 1:
            avg = loss_avg / loss_count if loss_count > 0 else 0.0
            elapsed = time.time() - t0
            it_per_sec = iteration / elapsed if elapsed > 0 else 0.0
            current_lr = scheduler.get_last_lr()[0]
            logger.info(
                "[%d/%d] loss=%.4f  avg_loss=%.4f  lr=%.6f  speed=%.1f it/s",
                iteration,
                num_iter,
                loss_val,
                avg,
                current_lr,
                it_per_sec,
            )
            loss_avg = 0.0
            loss_count = 0

        # ---------------------------------------------------------------
        # Validation & checkpointing
        # ---------------------------------------------------------------
        if iteration % val_interval == 0:
            logger.info("-" * 40)
            logger.info("Validation at iteration %d ...", iteration)

            accuracy, n_correct, n_total = validate(
                model, val_loader, converter, device, batch_max_length
            )

            logger.info(
                "  Accuracy: %.4f (%d / %d)", accuracy, n_correct, n_total
            )

            # Save latest checkpoint
            checkpoint = {
                "iteration": iteration,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "scheduler_state_dict": scheduler.state_dict(),
                "best_accuracy": best_accuracy,
                "accuracy": accuracy,
                "config": cfg,
                "charset": charset,
            }
            torch.save(checkpoint, str(latest_path))
            logger.info("  Saved latest -> %s", latest_path)

            # Save best model
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                checkpoint["best_accuracy"] = best_accuracy
                best_path = save_dir / "best_accuracy.pth"
                torch.save(checkpoint, str(best_path))
                logger.info(
                    "  🏆 New best accuracy: %.4f -> %s", best_accuracy, best_path
                )

            logger.info("-" * 40)
            model.train()

    # ---------------------------------------------------------------
    # 9. Final save
    # ---------------------------------------------------------------
    final_checkpoint = {
        "iteration": num_iter,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
        "best_accuracy": best_accuracy,
        "config": cfg,
        "charset": charset,
    }
    torch.save(final_checkpoint, str(latest_path))

    elapsed = time.time() - t0
    logger.info("=" * 60)
    logger.info("  Training complete!")
    logger.info("  Total time: %.1f seconds (%.1f min)", elapsed, elapsed / 60)
    logger.info("  Best accuracy: %.4f", best_accuracy)
    logger.info("  Models saved to: %s", save_dir)
    logger.info("=" * 60)


# ===================================================================
# CLI
# ===================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train CRNN model for Uzbek OCR (standalone).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=str,
        default="uzbek_config.yaml",
        help="Path to YAML config (default: uzbek_config.yaml)",
    )
    parser.add_argument(
        "--num_iter",
        type=int,
        default=None,
        help="Override number of training iterations",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=None,
        help="Override batch size",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "mps", "cuda"],
        help="Compute device (default: auto-detect)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume training from latest.pth checkpoint",
    )
    parser.add_argument(
        "--train_data",
        type=str,
        default=None,
        help="Override path to train LMDB directory",
    )
    parser.add_argument(
        "--val_data",
        type=str,
        default=None,
        help="Override path to validation LMDB directory",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(args)
