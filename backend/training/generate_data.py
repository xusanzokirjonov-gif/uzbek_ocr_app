#!/usr/bin/env python3
"""
Synthetic Data Generator for Uzbek OCR Training.

Generates synthetic text images for training an OCR model that recognizes
both Latin and Cyrillic Uzbek scripts. Uses Pillow (PIL) for reliable
text rendering with full control over augmentations.

Output format:
    data/raw/train/
        images/  (*.png)
        gt.txt   (image_filename<TAB>text_label)
    data/raw/val/
        images/
        gt.txt

Usage:
    python generate_data.py --count 10000 --val-count 2000
    python generate_data.py --count 50 --preview   # Show sample images
    python generate_data.py --count 100 --output-dir ./my_data
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import math
import os
import random
import string
import struct
import subprocess
import sys
import textwrap
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageTransform

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("uzbek_datagen")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Test strings to verify font glyph support
LATIN_TEST = "oʻgʻ Oʻzbekiston"
CYRILLIC_TEST = "Қағоз Ғишт Ҳақ Ўзбек"

# Uzbek-specific characters that MUST be renderable
LATIN_SPECIAL_CHARS = list("oʻgʻOʻGʻ")
CYRILLIC_SPECIAL_CHARS = list("ҚқҒғҲҳЎў")

# macOS font search paths
MACOS_FONT_DIRS = [
    "/System/Library/Fonts/",
    "/System/Library/Fonts/Supplemental/",
    "/Library/Fonts/",
    os.path.expanduser("~/Library/Fonts/"),
]

# Linux font search paths
LINUX_FONT_DIRS = [
    "/usr/share/fonts/",
    "/usr/local/share/fonts/",
    os.path.expanduser("~/.local/share/fonts/"),
    os.path.expanduser("~/.fonts/"),
]

# Preferred font family names (order matters — first found wins)
# These are known to have full Uzbek Latin+Cyrillic glyph support.
PREFERRED_FONTS = [
    # Cached Noto Sans (downloaded by this script) — guaranteed full support
    "NotoSans-Regular",
    "NotoSans-Bold",
    # System Noto Sans variants that cover Cyrillic
    "NotoSans",
    "Noto Sans",
    "NotoSerif",
    "Noto Serif",
    # Widely available system fonts known to support Uzbek Cyrillic
    "Arial Unicode",
    "ArialUnicodeMS",
    "Tahoma",
    "Verdana",
    "Times New Roman",
    "TimesNewRoman",
    "Trebuchet MS",
    "Microsoft Sans Serif",
    # Linux
    "DejaVuSans",
    "DejaVu Sans",
    "LiberationSans",
    "FreeSans",
]

# Google Fonts download URL for Noto Sans (supports Latin + Cyrillic)
NOTO_SANS_URL = (
    "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/"
    "NotoSans/full/ttf/NotoSans-Regular.ttf"
)
NOTO_SANS_BOLD_URL = (
    "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/"
    "NotoSans/full/ttf/NotoSans-Bold.ttf"
)

# Default image settings
DEFAULT_IMG_HEIGHT = 64
DEFAULT_TRAIN_COUNT = 10_000
DEFAULT_VAL_COUNT = 2_000

# Augmentation ranges
SKEW_RANGE = (-10, 10)  # degrees
BLUR_RADIUS_RANGE = (0.0, 1.5)
NOISE_INTENSITY_RANGE = (0, 25)

# Background colors / text colors
BG_COLORS = [
    (255, 255, 255),  # white
    (245, 245, 245),  # off-white
    (240, 240, 230),  # light beige
    (230, 230, 250),  # lavender
    (255, 250, 240),  # floral white
    (245, 255, 250),  # mint cream
    (255, 248, 220),  # cornsilk
    (240, 248, 255),  # alice blue
    (255, 245, 238),  # seashell
    (250, 250, 210),  # light goldenrod yellow
    (200, 200, 200),  # light gray
    (180, 180, 200),  # grayish blue
]

TEXT_COLORS = [
    (0, 0, 0),        # black
    (30, 30, 30),     # near-black
    (50, 50, 50),     # dark gray
    (10, 10, 80),     # dark blue
    (60, 20, 20),     # dark red-brown
    (20, 50, 20),     # dark green
    (80, 80, 80),     # medium gray
]


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class FontInfo:
    """Metadata for a validated font."""
    path: str
    name: str
    supports_latin: bool = False
    supports_cyrillic: bool = False


@dataclass
class AugmentationConfig:
    """Configuration for image augmentations."""
    skew_range: Tuple[float, float] = SKEW_RANGE
    blur_range: Tuple[float, float] = BLUR_RADIUS_RANGE
    noise_range: Tuple[int, int] = NOISE_INTENSITY_RANGE
    apply_skew_prob: float = 0.4
    apply_blur_prob: float = 0.3
    apply_noise_prob: float = 0.4
    apply_distortion_prob: float = 0.15
    apply_shadow_prob: float = 0.1
    apply_invert_prob: float = 0.05  # dark bg, light text


# ---------------------------------------------------------------------------
# Font Management
# ---------------------------------------------------------------------------
def _get_font_dirs() -> List[str]:
    """Return font directories for the current platform."""
    if sys.platform == "darwin":
        return MACOS_FONT_DIRS
    elif sys.platform.startswith("linux"):
        return LINUX_FONT_DIRS
    else:
        # Windows or other — best effort
        win_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        return [win_fonts]


def _render_char_hash(font: "ImageFont.FreeTypeFont", ch: str, size: int) -> bytes:
    """Render a single character and return a hash of the pixel data."""
    img = Image.new("L", (size * 2, size * 2), 255)
    draw = ImageDraw.Draw(img)
    draw.text((2, 2), ch, font=font, fill=0)
    return bytes(np.array(img).flatten().tolist())


def _test_font_glyph_support(
    font_path: str,
    test_chars: Sequence[str],
    size: int = 32,
) -> bool:
    """
    Test whether a font can render all characters in *test_chars* WITHOUT
    falling back to a tofu/replacement box.

    Strategy: render a character that NO font has a real glyph for
    (U+FFF0, private-use area) to capture the font's "tofu fingerprint".
    Then render each test char and compare pixel hashes — if they match the
    tofu fingerprint, the glyph is missing even if the bbox is non-zero.
    """
    try:
        pil_font = ImageFont.truetype(font_path, size)
    except (OSError, IOError):
        return False

    # Capture tofu fingerprint using a guaranteed-missing codepoint
    TOFU_PROBE = "\uFFF0"  # Specials block — no font has a real glyph here
    tofu_hash = _render_char_hash(pil_font, TOFU_PROBE, size)

    for ch in test_chars:
        try:
            # Fast bbox pre-check
            bbox = pil_font.getbbox(ch)
            if bbox is None or (bbox[2] - bbox[0]) <= 0 or (bbox[3] - bbox[1]) <= 0:
                return False

            # Render and compare with tofu fingerprint
            char_pixels = _render_char_hash(pil_font, ch, size)

            if char_pixels == tofu_hash:
                # Glyph renders identically to the tofu replacement — missing!
                return False

            # Also verify the image is not entirely white (blank)
            arr = np.frombuffer(char_pixels, dtype=np.uint8)
            if arr.min() == 255:
                return False

        except Exception:
            return False
    return True


def find_system_fonts() -> List[FontInfo]:
    """
    Scan system font directories and return fonts that support Uzbek text.

    Returns a list of FontInfo objects, with flags indicating Latin/Cyrillic
    support for Uzbek-specific characters.
    """
    fonts: List[FontInfo] = []
    seen_paths: set[str] = set()

    font_dirs = _get_font_dirs()
    for font_dir in font_dirs:
        if not os.path.isdir(font_dir):
            continue
        for root, _dirs, files in os.walk(font_dir):
            for fname in files:
                if not fname.lower().endswith((".ttf", ".otf", ".ttc")):
                    continue
                full_path = os.path.join(root, fname)
                if full_path in seen_paths:
                    continue
                seen_paths.add(full_path)

                supports_lat = _test_font_glyph_support(
                    full_path, LATIN_SPECIAL_CHARS
                )
                supports_cyr = _test_font_glyph_support(
                    full_path, CYRILLIC_SPECIAL_CHARS
                )

                if supports_lat or supports_cyr:
                    font_name = os.path.splitext(fname)[0]
                    fonts.append(FontInfo(
                        path=full_path,
                        name=font_name,
                        supports_latin=supports_lat,
                        supports_cyrillic=supports_cyr,
                    ))
                    logger.debug(
                        "Found font: %s  lat=%s cyr=%s",
                        font_name, supports_lat, supports_cyr,
                    )

    # Sort: prefer fonts whose names match PREFERRED_FONTS first
    def _sort_key(fi: FontInfo) -> Tuple[int, str]:
        for idx, pref in enumerate(PREFERRED_FONTS):
            if pref.lower().replace(" ", "") in fi.name.lower().replace(" ", ""):
                return (idx, fi.name)
        return (len(PREFERRED_FONTS), fi.name)

    fonts.sort(key=_sort_key)
    return fonts


def download_noto_sans(cache_dir: Path) -> List[FontInfo]:
    """
    Download Noto Sans Regular + Bold from GitHub and cache locally.

    Returns list of FontInfo for the downloaded fonts.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    fonts: List[FontInfo] = []

    for url, fname in [
        (NOTO_SANS_URL, "NotoSans-Regular.ttf"),
        (NOTO_SANS_BOLD_URL, "NotoSans-Bold.ttf"),
    ]:
        dest = cache_dir / fname
        if not dest.exists():
            logger.info("Downloading %s …", fname)
            try:
                urllib.request.urlretrieve(url, str(dest))
                logger.info("Saved to %s", dest)
            except Exception as exc:
                logger.warning("Failed to download %s: %s", fname, exc)
                continue
        else:
            logger.info("Using cached font: %s", dest)

        if dest.exists():
            supports_lat = _test_font_glyph_support(
                str(dest), LATIN_SPECIAL_CHARS
            )
            supports_cyr = _test_font_glyph_support(
                str(dest), CYRILLIC_SPECIAL_CHARS
            )
            fonts.append(FontInfo(
                path=str(dest),
                name=fname.replace(".ttf", ""),
                supports_latin=supports_lat,
                supports_cyrillic=supports_cyr,
            ))

    return fonts


def resolve_fonts(cache_dir: Path) -> Tuple[List[FontInfo], List[FontInfo]]:
    """
    Find and validate fonts for both Latin and Cyrillic Uzbek text.

    Returns:
        (latin_fonts, cyrillic_fonts)

    If no system fonts are found, downloads Noto Sans as fallback.
    """
    logger.info("Scanning system fonts for Uzbek character support…")
    all_fonts = find_system_fonts()

    latin_fonts = [f for f in all_fonts if f.supports_latin]
    cyrillic_fonts = [f for f in all_fonts if f.supports_cyrillic]

    if latin_fonts:
        logger.info(
            "Found %d system font(s) with Latin Uzbek support: %s",
            len(latin_fonts),
            ", ".join(f.name for f in latin_fonts[:5]),
        )
    if cyrillic_fonts:
        logger.info(
            "Found %d system font(s) with Cyrillic Uzbek support: %s",
            len(cyrillic_fonts),
            ", ".join(f.name for f in cyrillic_fonts[:5]),
        )

    # Fallback: download Noto Sans
    if not latin_fonts or not cyrillic_fonts:
        logger.info("Downloading Noto Sans as fallback font…")
        noto_fonts = download_noto_sans(cache_dir)
        for nf in noto_fonts:
            if nf.supports_latin and nf not in latin_fonts:
                latin_fonts.append(nf)
            if nf.supports_cyrillic and nf not in cyrillic_fonts:
                cyrillic_fonts.append(nf)

    if not latin_fonts:
        logger.error("No fonts found that support Uzbek Latin characters!")
    if not cyrillic_fonts:
        logger.error("No fonts found that support Uzbek Cyrillic characters!")

    return latin_fonts, cyrillic_fonts


# ---------------------------------------------------------------------------
# Word List Loader
# ---------------------------------------------------------------------------
def load_words(words_file: Path) -> Tuple[List[str], List[str]]:
    """
    Load words from the word list file, separating Latin and Cyrillic entries.

    Returns:
        (latin_words, cyrillic_words)
    """
    if not words_file.exists():
        logger.error("Word list not found: %s", words_file)
        sys.exit(1)

    latin_words: List[str] = []
    cyrillic_words: List[str] = []

    with open(words_file, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Determine script by checking for Cyrillic characters
            has_cyrillic = any("\u0400" <= ch <= "\u04FF" for ch in line)
            if has_cyrillic:
                cyrillic_words.append(line)
            else:
                latin_words.append(line)

    logger.info(
        "Loaded %d Latin words and %d Cyrillic words from %s",
        len(latin_words), len(cyrillic_words), words_file.name,
    )
    return latin_words, cyrillic_words


def make_text_sample(
    words: List[str],
    max_words: int = 3,
) -> str:
    """Create a text sample of 1–max_words words from the word list."""
    n = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15], k=1)[0]
    n = min(n, max_words, len(words))
    chosen = random.sample(words, n)
    return " ".join(chosen)


# ---------------------------------------------------------------------------
# Image Generation Engine
# ---------------------------------------------------------------------------
def _add_gaussian_noise(img: Image.Image, intensity: int) -> Image.Image:
    """Add Gaussian noise to an image."""
    arr = np.array(img, dtype=np.int16)
    noise = np.random.normal(0, intensity, arr.shape).astype(np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _add_shadow(img: Image.Image) -> Image.Image:
    """Add a subtle gradient shadow effect."""
    w, h = img.size
    arr = np.array(img, dtype=np.float32)

    # Random gradient direction
    direction = random.choice(["left", "right", "top", "bottom"])
    factor = random.uniform(0.7, 0.95)

    if direction == "left":
        gradient = np.linspace(factor, 1.0, w)
        gradient = np.tile(gradient, (h, 1))
    elif direction == "right":
        gradient = np.linspace(1.0, factor, w)
        gradient = np.tile(gradient, (h, 1))
    elif direction == "top":
        gradient = np.linspace(factor, 1.0, h)
        gradient = np.tile(gradient.reshape(-1, 1), (1, w))
    else:
        gradient = np.linspace(1.0, factor, h)
        gradient = np.tile(gradient.reshape(-1, 1), (1, w))

    if len(arr.shape) == 3:
        gradient = gradient[:, :, np.newaxis]

    arr = np.clip(arr * gradient, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _apply_perspective_distortion(img: Image.Image) -> Image.Image:
    """Apply subtle perspective distortion."""
    w, h = img.size
    # Small random offsets for corners
    max_shift = int(min(w, h) * 0.05)  # 5% of smaller dimension

    # Define source quad (original corners)
    # Apply to target quad (slightly shifted corners)
    dx = [random.randint(-max_shift, max_shift) for _ in range(4)]
    dy = [random.randint(-max_shift, max_shift) for _ in range(4)]

    coeffs = _find_perspective_coeffs(
        pa=[
            (dx[0], dy[0]),
            (w + dx[1], dy[1]),
            (w + dx[2], h + dy[2]),
            (dx[3], h + dy[3]),
        ],
        pb=[
            (0, 0),
            (w, 0),
            (w, h),
            (0, h),
        ],
    )

    return img.transform((w, h), ImageTransform.PerspectiveTransform(coeffs))


def _find_perspective_coeffs(
    pa: List[Tuple[float, float]],
    pb: List[Tuple[float, float]],
) -> List[float]:
    """Calculate perspective transform coefficients."""
    matrix = []
    for s, d in zip(pa, pb):
        matrix.append([d[0], d[1], 1, 0, 0, 0, -s[0] * d[0], -s[0] * d[1]])
        matrix.append([0, 0, 0, d[0], d[1], 1, -s[1] * d[0], -s[1] * d[1]])

    A = np.array(matrix, dtype=np.float64)
    B = np.array([coord for pair in pa for coord in pair], dtype=np.float64)

    try:
        res = np.linalg.solve(A, B)
    except np.linalg.LinAlgError:
        return [1, 0, 0, 0, 1, 0, 0, 0]  # Identity transform

    return list(res)


def generate_text_image(
    text: str,
    font: ImageFont.FreeTypeFont,
    img_height: int = DEFAULT_IMG_HEIGHT,
    aug_config: AugmentationConfig = AugmentationConfig(),
) -> Image.Image:
    """
    Render *text* into a synthetic training image.

    The image is sized to fit the text with padding, then augmented with
    random effects (blur, skew, noise, distortion, shadows).

    Args:
        text: The text string to render.
        font: A PIL FreeTypeFont object.
        img_height: Target image height in pixels.
        aug_config: Augmentation parameters.

    Returns:
        A PIL Image in RGB mode.
    """
    # --- Choose colors ---
    if random.random() < aug_config.apply_invert_prob:
        # Inverted: dark background, light text
        bg_color = random.choice(TEXT_COLORS)
        text_color = random.choice(BG_COLORS)
    else:
        bg_color = random.choice(BG_COLORS)
        text_color = random.choice(TEXT_COLORS)

    # --- Measure text ---
    # Create a temporary large canvas to measure text
    tmp_img = Image.new("RGB", (2000, 200), bg_color)
    tmp_draw = ImageDraw.Draw(tmp_img)
    bbox = tmp_draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    if text_w <= 0 or text_h <= 0:
        # Fallback for empty/missing glyphs
        text_w, text_h = 100, img_height - 10

    # --- Compute image dimensions ---
    # Scale font to fill ~70-85% of image height
    target_text_h = int(img_height * random.uniform(0.55, 0.75))
    scale = target_text_h / max(text_h, 1)
    scaled_w = int(text_w * scale)
    scaled_h = int(text_h * scale)

    # Padding
    pad_x = random.randint(5, max(6, int(scaled_w * 0.15)))
    pad_y = max(2, (img_height - scaled_h) // 2)

    canvas_w = scaled_w + 2 * pad_x
    canvas_h = img_height

    # Minimum width
    canvas_w = max(canvas_w, img_height)

    # --- Create canvas and render text ---
    img = Image.new("RGB", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(img)

    # Re-create font at scaled size
    font_size = max(8, int(font.size * scale))
    try:
        scaled_font = ImageFont.truetype(font.path, font_size)
    except (AttributeError, OSError):
        scaled_font = font

    # Center text vertically, slight random horizontal offset
    x_offset = pad_x + random.randint(-2, 2)
    y_offset = pad_y + random.randint(-2, 2)
    y_offset = max(1, min(y_offset, canvas_h - scaled_h - 1))

    draw.text((x_offset, y_offset), text, font=scaled_font, fill=text_color)

    # --- Apply augmentations ---

    # 1. Skew (rotation)
    if random.random() < aug_config.apply_skew_prob:
        angle = random.uniform(*aug_config.skew_range)
        # Expand=True so we don't crop text, then resize back
        img = img.rotate(
            angle,
            resample=Image.BICUBIC,
            expand=True,
            fillcolor=bg_color,
        )
        # Resize height back to target
        new_w = int(img.width * img_height / img.height)
        img = img.resize((max(new_w, 10), img_height), Image.BICUBIC)

    # 2. Perspective distortion
    if random.random() < aug_config.apply_distortion_prob:
        img = _apply_perspective_distortion(img)

    # 3. Shadow effect
    if random.random() < aug_config.apply_shadow_prob:
        img = _add_shadow(img)

    # 4. Gaussian noise
    if random.random() < aug_config.apply_noise_prob:
        intensity = random.randint(*aug_config.noise_range)
        if intensity > 0:
            img = _add_gaussian_noise(img, intensity)

    # 5. Blur
    if random.random() < aug_config.apply_blur_prob:
        radius = random.uniform(*aug_config.blur_range)
        if radius > 0.1:
            img = img.filter(ImageFilter.GaussianBlur(radius=radius))

    return img


# ---------------------------------------------------------------------------
# Data Pipeline
# ---------------------------------------------------------------------------
@dataclass
class GenerationStats:
    """Track generation statistics."""
    total_generated: int = 0
    latin_count: int = 0
    cyrillic_count: int = 0
    skipped_errors: int = 0
    fonts_used: set = field(default_factory=set)


def generate_dataset(
    output_dir: Path,
    split: str,
    count: int,
    latin_words: List[str],
    cyrillic_words: List[str],
    latin_fonts: List[FontInfo],
    cyrillic_fonts: List[FontInfo],
    img_height: int = DEFAULT_IMG_HEIGHT,
    aug_config: AugmentationConfig = AugmentationConfig(),
) -> GenerationStats:
    """
    Generate a dataset split (train or val).

    Creates:
        {output_dir}/{split}/images/*.png
        {output_dir}/{split}/gt.txt

    Args:
        output_dir: Root output directory (e.g., data/raw).
        split: Split name ("train" or "val").
        count: Number of images to generate.
        latin_words: Latin-script word list.
        cyrillic_words: Cyrillic-script word list.
        latin_fonts: Validated fonts for Latin text.
        cyrillic_fonts: Validated fonts for Cyrillic text.
        img_height: Target image height.
        aug_config: Augmentation config.

    Returns:
        GenerationStats with summary.
    """
    try:
        from tqdm import tqdm
    except ImportError:
        logger.warning("tqdm not installed — no progress bar.")
        tqdm = None  # type: ignore[assignment]

    split_dir = output_dir / split
    images_dir = split_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    gt_path = split_dir / "gt.txt"
    stats = GenerationStats()

    # Decide ratio of Latin vs Cyrillic
    # If either word list or font list is empty, generate 100% of the other
    has_latin = bool(latin_words and latin_fonts)
    has_cyrillic = bool(cyrillic_words and cyrillic_fonts)

    if not has_latin and not has_cyrillic:
        logger.error("No words or fonts available for either script!")
        return stats

    # Pre-load fonts at a base size (will be rescaled per image)
    base_font_size = 40
    latin_pil_fonts: List[ImageFont.FreeTypeFont] = []
    for fi in latin_fonts:
        try:
            latin_pil_fonts.append(ImageFont.truetype(fi.path, base_font_size))
        except Exception as exc:
            logger.warning("Cannot load font %s: %s", fi.name, exc)

    cyrillic_pil_fonts: List[ImageFont.FreeTypeFont] = []
    for fi in cyrillic_fonts:
        try:
            cyrillic_pil_fonts.append(ImageFont.truetype(fi.path, base_font_size))
        except Exception as exc:
            logger.warning("Cannot load font %s: %s", fi.name, exc)

    logger.info(
        "Generating %d %s images (lat_fonts=%d, cyr_fonts=%d) → %s",
        count, split, len(latin_pil_fonts), len(cyrillic_pil_fonts), split_dir,
    )

    iterator = range(count)
    if tqdm is not None:
        iterator = tqdm(iterator, desc=f"  {split}", unit="img", ncols=80)

    gt_lines: List[str] = []

    for i in iterator:
        # Choose script
        if has_latin and has_cyrillic:
            use_cyrillic = random.random() < 0.5
        elif has_cyrillic:
            use_cyrillic = True
        else:
            use_cyrillic = False

        if use_cyrillic:
            text = make_text_sample(cyrillic_words)
            font = random.choice(cyrillic_pil_fonts)
            stats.cyrillic_count += 1
        else:
            text = make_text_sample(latin_words)
            font = random.choice(latin_pil_fonts)
            stats.latin_count += 1

        # Generate image
        try:
            img = generate_text_image(
                text=text,
                font=font,
                img_height=img_height,
                aug_config=aug_config,
            )
        except Exception as exc:
            logger.debug("Error generating image %d: %s", i, exc)
            stats.skipped_errors += 1
            continue

        # Save
        img_filename = f"{split}_{i:06d}.png"
        img_path = images_dir / img_filename
        img.save(str(img_path), "PNG")

        gt_lines.append(f"{img_filename}\t{text}")
        stats.total_generated += 1
        stats.fonts_used.add(font.path if hasattr(font, "path") else "unknown")

    # Write ground truth file
    with open(gt_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(gt_lines))
        fh.write("\n")

    logger.info(
        "%s complete: %d images (%d Latin, %d Cyrillic, %d errors)",
        split,
        stats.total_generated,
        stats.latin_count,
        stats.cyrillic_count,
        stats.skipped_errors,
    )

    return stats


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------
def preview_samples(
    output_dir: Path,
    n: int = 20,
) -> None:
    """
    Display a grid of sample generated images using matplotlib.

    Falls back to opening individual images if matplotlib is not available.
    """
    # Gather sample images from train split
    train_images_dir = output_dir / "train" / "images"
    gt_path = output_dir / "train" / "gt.txt"

    if not train_images_dir.exists() or not gt_path.exists():
        logger.warning("No training data found at %s", train_images_dir)
        return

    # Load ground truth
    gt_map: dict[str, str] = {}
    with open(gt_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if "\t" in line:
                fname, label = line.split("\t", 1)
                gt_map[fname] = label

    # Pick random samples
    all_images = sorted(train_images_dir.glob("*.png"))
    if not all_images:
        logger.warning("No images found in %s", train_images_dir)
        return

    samples = random.sample(all_images, min(n, len(all_images)))

    try:
        import matplotlib

        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt

        cols = 4
        rows = math.ceil(len(samples) / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(16, 3 * rows))
        if rows == 1:
            axes = [axes] if cols == 1 else list(axes)
        else:
            axes = [ax for row in axes for ax in row]

        for idx, img_path in enumerate(samples):
            img = Image.open(img_path)
            label = gt_map.get(img_path.name, "???")
            axes[idx].imshow(np.array(img))
            axes[idx].set_title(label, fontsize=9)
            axes[idx].axis("off")

        # Hide unused axes
        for idx in range(len(samples), len(axes)):
            axes[idx].axis("off")

        plt.tight_layout()
        preview_path = output_dir / "preview_samples.png"
        plt.savefig(str(preview_path), dpi=150, bbox_inches="tight")
        plt.close()
        logger.info("Preview saved to %s", preview_path)
        logger.info("Opening preview…")

        # Open on macOS
        if sys.platform == "darwin":
            subprocess.run(["open", str(preview_path)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(preview_path)], check=False)

    except ImportError:
        logger.warning(
            "matplotlib not available. Showing individual images instead."
        )
        for img_path in samples[:5]:
            label = gt_map.get(img_path.name, "???")
            logger.info("  %s → '%s'", img_path.name, label)
            if sys.platform == "darwin":
                subprocess.run(["open", str(img_path)], check=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic Uzbek OCR training data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python generate_data.py --count 10000 --val-count 2000
              python generate_data.py --count 50 --preview
              python generate_data.py --count 100 --output-dir ./my_data --img-height 48
        """),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_TRAIN_COUNT,
        help=f"Number of training images (default: {DEFAULT_TRAIN_COUNT})",
    )
    parser.add_argument(
        "--val-count",
        type=int,
        default=DEFAULT_VAL_COUNT,
        help=f"Number of validation images (default: {DEFAULT_VAL_COUNT})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: data/raw/ relative to script)",
    )
    parser.add_argument(
        "--words-file",
        type=str,
        default=None,
        help="Path to uzbek_words.txt (default: auto-detect near script)",
    )
    parser.add_argument(
        "--img-height",
        type=int,
        default=DEFAULT_IMG_HEIGHT,
        help=f"Image height in pixels (default: {DEFAULT_IMG_HEIGHT})",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show preview of generated samples after generation",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for synthetic data generation."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        logger.info("Random seed: %d", args.seed)

    # --- Resolve paths ---
    script_dir = Path(__file__).resolve().parent
    backend_dir = script_dir.parent  # backend/training/ → backend/

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = backend_dir / "data" / "raw"

    if args.words_file:
        words_file = Path(args.words_file).resolve()
    else:
        words_file = script_dir / "uzbek_words.txt"

    font_cache_dir = backend_dir / "data" / "fonts"

    logger.info("=" * 60)
    logger.info("Uzbek OCR Synthetic Data Generator")
    logger.info("=" * 60)
    logger.info("Output dir:  %s", output_dir)
    logger.info("Words file:  %s", words_file)
    logger.info("Train count: %d", args.count)
    logger.info("Val count:   %d", args.val_count)
    logger.info("Image height: %dpx", args.img_height)
    logger.info("-" * 60)

    # --- Load words ---
    latin_words, cyrillic_words = load_words(words_file)
    if not latin_words and not cyrillic_words:
        logger.error("No words loaded — cannot generate data.")
        sys.exit(1)

    # --- Resolve fonts ---
    latin_fonts, cyrillic_fonts = resolve_fonts(font_cache_dir)

    if not latin_fonts and not cyrillic_fonts:
        logger.error(
            "No usable fonts found! Please install a Unicode font like "
            "Noto Sans that supports Uzbek Latin (ʻ) and Cyrillic (Қ Ғ Ҳ Ў)."
        )
        sys.exit(1)

    logger.info("-" * 60)
    logger.info("Fonts for Latin: %s", ", ".join(f.name for f in latin_fonts[:3]))
    logger.info("Fonts for Cyrillic: %s", ", ".join(f.name for f in cyrillic_fonts[:3]))
    logger.info("-" * 60)

    aug_config = AugmentationConfig()

    # --- Generate training data ---
    train_stats = generate_dataset(
        output_dir=output_dir,
        split="train",
        count=args.count,
        latin_words=latin_words,
        cyrillic_words=cyrillic_words,
        latin_fonts=latin_fonts,
        cyrillic_fonts=cyrillic_fonts,
        img_height=args.img_height,
        aug_config=aug_config,
    )

    # --- Generate validation data ---
    val_stats = generate_dataset(
        output_dir=output_dir,
        split="val",
        count=args.val_count,
        latin_words=latin_words,
        cyrillic_words=cyrillic_words,
        latin_fonts=latin_fonts,
        cyrillic_fonts=cyrillic_fonts,
        img_height=args.img_height,
        aug_config=aug_config,
    )

    # --- Summary ---
    total = train_stats.total_generated + val_stats.total_generated
    logger.info("=" * 60)
    logger.info("GENERATION COMPLETE")
    logger.info(
        "  Total images: %d  (train=%d, val=%d)",
        total, train_stats.total_generated, val_stats.total_generated,
    )
    logger.info(
        "  Latin: %d   Cyrillic: %d",
        train_stats.latin_count + val_stats.latin_count,
        train_stats.cyrillic_count + val_stats.cyrillic_count,
    )
    logger.info(
        "  Errors skipped: %d",
        train_stats.skipped_errors + val_stats.skipped_errors,
    )
    logger.info("  Output: %s", output_dir)
    logger.info("=" * 60)

    # --- Preview ---
    if args.preview:
        preview_samples(output_dir, n=20)


if __name__ == "__main__":
    main()
