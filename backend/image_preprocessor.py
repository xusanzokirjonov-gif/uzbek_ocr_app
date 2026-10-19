"""
image_preprocessor.py
=====================
Умный препроцессинг изображений для улучшения точности EasyOCR.

Проблема: EasyOCR обучен на тёмном тексте на светлом фоне.
Скриншоты тёмной темы (светлый текст на тёмном фоне) дают плохой результат.

Решение:
  1. Определяем среднюю яркость фона изображения
  2. Если фон тёмный → инвертируем изображение
  3. Применяем CLAHE для улучшения локального контраста
  4. При необходимости увеличиваем разрешение (upscaling) для мелкого текста
"""

import logging
import numpy as np
from PIL import Image, ImageOps, ImageEnhance
import cv2

logger = logging.getLogger("uzbek_ocr.preprocess")


def preprocess_for_ocr(pil_image: Image.Image) -> tuple[Image.Image, dict]:
    """
    Умный препроцессинг изображения перед подачей в EasyOCR.

    Args:
        pil_image: PIL Image (должен быть в режиме RGB)

    Returns:
        (processed_image, info_dict) — обработанное изображение и словарь с метаданными
    """
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    info = {
        "inverted": False,
        "upscaled": False,
        "clahe_applied": False,
        "original_size": pil_image.size,
        "processed_size": pil_image.size,
    }

    img_array = np.array(pil_image)

    # ── 1. Определяем нужна ли инверсия (тёмный фон?) ─────────────────────────
    if _is_dark_background(img_array):
        logger.info("[Preprocess] Dark background detected — inverting image")
        pil_image = ImageOps.invert(pil_image)
        img_array = np.array(pil_image)
        info["inverted"] = True

    # ── 2. Upscaling для мелкого текста (< 32px высота строки) ────────────────
    w, h = pil_image.size
    # Если изображение маленькое — масштабируем до минимального размера
    min_side = min(w, h)
    if min_side < 400:
        scale = max(2.0, 800 / min_side)
        new_w = int(w * scale)
        new_h = int(h * scale)
        pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
        img_array = np.array(pil_image)
        info["upscaled"] = True
        info["processed_size"] = pil_image.size
        logger.info(f"[Preprocess] Upscaled {w}x{h} → {new_w}x{new_h} (scale={scale:.1f}x)")

    # ── 3. CLAHE — улучшение локального контраста ──────────────────────────────
    img_array = _apply_clahe(img_array)
    info["clahe_applied"] = True

    processed = Image.fromarray(img_array)
    info["processed_size"] = processed.size

    logger.info(
        f"[Preprocess] Done: inverted={info['inverted']}, "
        f"upscaled={info['upscaled']}, size={info['processed_size']}"
    )

    return processed, info


def _is_dark_background(img_array: np.ndarray, threshold: float = 100.0) -> bool:
    """
    Определяет, тёмный ли фон изображения.

    Алгоритм:
      - Конвертируем в grayscale
      - Берём медиану пикселей по краевой зоне (10% от краёв)
        (центр может быть занят текстом, края — обычно фон)
      - Если медиана < threshold → фон тёмный

    Args:
        img_array: numpy array RGB изображения
        threshold: порог яркости (0–255), ниже → тёмный фон

    Returns:
        True если фон тёмный
    """
    gray = np.mean(img_array, axis=2)  # RGB → grayscale через среднее
    h, w = gray.shape

    # Берём пиксели по периметру (10% от каждой стороны)
    border_size_h = max(1, h // 10)
    border_size_w = max(1, w // 10)

    top    = gray[:border_size_h, :]
    bottom = gray[h - border_size_h:, :]
    left   = gray[:, :border_size_w]
    right  = gray[:, w - border_size_w:]

    border_pixels = np.concatenate([
        top.ravel(), bottom.ravel(), left.ravel(), right.ravel()
    ])

    median_brightness = float(np.median(border_pixels))
    logger.debug(f"[Preprocess] Border median brightness: {median_brightness:.1f}")

    return median_brightness < threshold


def _apply_clahe(img_array: np.ndarray) -> np.ndarray:
    """
    Применяет CLAHE (Contrast Limited Adaptive Histogram Equalization)
    для улучшения локального контраста.

    Работает на L-канале LAB цветового пространства чтобы не искажать цвета.
    """
    try:
        # Конвертируем RGB → LAB
        lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
        l_channel, a, b = cv2.split(lab)

        # Применяем CLAHE к L-каналу (яркость)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_clahe = clahe.apply(l_channel)

        # Собираем обратно
        lab_clahe = cv2.merge((l_clahe, a, b))
        result = cv2.cvtColor(lab_clahe, cv2.COLOR_LAB2RGB)
        return result
    except Exception as e:
        logger.warning(f"[Preprocess] CLAHE failed: {e}, returning original")
        return img_array
