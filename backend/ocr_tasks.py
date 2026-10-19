"""
ocr_tasks.py
============
Celery-задачи для асинхронной OCR-обработки изображений.

OCR-пайплайн:
  1. Загрузка изображения из временного файла.
  2. Предобработка (RGB-конвертация, numpy-массив).
  3. Детекция текстовых регионов (CRAFT).
  4. Распознавание двумя EasyOCR-ридерами (Dual-Reader Strategy).
  5. Нормализация гомоглифов (HomoglyphNormalizer / stub).
  6. Исправление орфографии (UzbekSpellingCorrector / stub).
  7. Реконструкция разметки (LayoutReconstructor / stub).
  8. Конвертация между алфавитами (Latin <-> Cyrillic).
"""

import io
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from celery_app import celery_app

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    from homoglyph_normalizer import HomoglyphNormalizer, Script, detect_script
    NORMALIZER_AVAILABLE = True
except ImportError:
    NORMALIZER_AVAILABLE = False

try:
    from spelling_corrector import UzbekSpellingCorrector
    CORRECTOR_AVAILABLE = True
except ImportError:
    CORRECTOR_AVAILABLE = False

try:
    from layout_reconstructor import reconstruct_layout, reconstruct_layout_with_meta
    RECONSTRUCTOR_AVAILABLE = True
except ImportError:
    RECONSTRUCTOR_AVAILABLE = False

# ─── Логирование ──────────────────────────────────────────────────────────────

logger = logging.getLogger("uzbek_ocr.tasks")

# ─── Пути ─────────────────────────────────────────────────────────────────────

BASE_DIR        = Path(__file__).resolve().parent
MODEL_DIR       = BASE_DIR / "model"
DICT_PATH       = MODEL_DIR / "uzwords.txt"
LATIN_DICT_PATH = MODEL_DIR / "uzwords_latin.txt"

# ─── Singleton-кэш ридеров ────────────────────────────────────────────────────

_latin_reader:    Optional["easyocr.Reader"]        = None
_cyrillic_reader: Optional["easyocr.Reader"]        = None
_normalizer:      Optional["HomoglyphNormalizer"]   = None
_corrector:       Optional["UzbekSpellingCorrector"] = None


def _get_readers() -> tuple:
    """Ленивая инициализация EasyOCR ридеров (singleton)."""
    global _latin_reader, _cyrillic_reader

    if _latin_reader is None or _cyrillic_reader is None:
        if not EASYOCR_AVAILABLE:
            logger.warning("EasyOCR not available — using stub readers")
            _latin_reader    = None
            _cyrillic_reader = None
        else:
            logger.info("Initializing EasyOCR readers (first call, may take 60s)...")
            _latin_reader = easyocr.Reader(
                lang_list=["uz", "en"],
                gpu=False,
                model_storage_directory=str(MODEL_DIR),
                verbose=False,
                quantize=False,
            )
            _cyrillic_reader = easyocr.Reader(
                lang_list=["ru", "be", "tjk", "en"],
                gpu=False,
                model_storage_directory=str(MODEL_DIR),
                verbose=False,
                quantize=False,
            )
            logger.info("EasyOCR readers ready (FP32, quantize=False, Cyrillic includes ru, be, tjk, en).")

    return _latin_reader, _cyrillic_reader


def _get_normalizer() -> Optional["HomoglyphNormalizer"]:
    """Ленивая инициализация нормализатора гомоглифов."""
    global _normalizer
    if _normalizer is None:
        if NORMALIZER_AVAILABLE:
            _normalizer = HomoglyphNormalizer(prefer_standard_apostrophe=True)
        else:
            logger.warning("HomoglyphNormalizer not available — using stub (passthrough)")
    return _normalizer


def _get_corrector() -> Optional["UzbekSpellingCorrector"]:
    """Ленивая инициализация исправителя орфографии."""
    global _corrector
    if _corrector is None:
        if CORRECTOR_AVAILABLE and DICT_PATH.exists():
            _corrector = UzbekSpellingCorrector(
                dict_path=DICT_PATH,
                max_distance=1.5,
                latin_dict_path=LATIN_DICT_PATH if LATIN_DICT_PATH.exists() else None,
            )
        else:
            logger.warning("UzbekSpellingCorrector not available — using stub (passthrough)")
    return _corrector


# ─── Вспомогательные функции ──────────────────────────────────────────────────

_CYRILLIC_CHARS = frozenset(
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    "ЎўҚқҒғҲҳ"
)


def _is_valid_block(text: str, conf: float) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    # Отсеиваем галлюцинации детектора (пустые участки/текстуры дают conf < 0.15)
    if conf < 0.15:
        return False
    return True


def _merge_dual_reader_results(
    latin_results: list,
    cyrillic_results: list,
) -> tuple:
    """
    Объединяет результаты двух ридеров, выбирая лучший блок.
    Фильтрует пустые и шумовые блоки.
    Определяет общий алфавит по реальному количеству букв, а не блоков.
    """
    merged = []
    min_len = min(len(latin_results), len(cyrillic_results))

    for i in range(min_len):
        lat_bbox, lat_text, lat_conf = latin_results[i]
        cyr_bbox, cyr_text, cyr_conf = cyrillic_results[i]

        lat_valid = _is_valid_block(lat_text, lat_conf)
        cyr_valid = _is_valid_block(cyr_text, cyr_conf)

        if not lat_valid and not cyr_valid:
            continue

        if cyr_valid and not lat_valid:
            merged.append((cyr_bbox, cyr_text, cyr_conf))
            continue

        if lat_valid and not cyr_valid:
            merged.append((lat_bbox, lat_text, lat_conf))
            continue

        # Оба варианта валидны — выбираем лучший
        cyr_char_count = sum(1 for ch in cyr_text if ch in _CYRILLIC_CHARS)
        if cyr_char_count > 0 and (cyr_conf >= lat_conf or cyr_conf > 0.25):
            merged.append((cyr_bbox, cyr_text, cyr_conf))
        elif lat_conf > cyr_conf and lat_conf > 0.25:
            merged.append((lat_bbox, lat_text, lat_conf))
        elif cyr_conf >= lat_conf:
            merged.append((cyr_bbox, cyr_text, cyr_conf))
        else:
            merged.append((lat_bbox, lat_text, lat_conf))

    for i in range(min_len, len(latin_results)):
        bbox, text, conf = latin_results[i]
        if _is_valid_block(text, conf):
            merged.append((bbox, text, conf))

    for i in range(min_len, len(cyrillic_results)):
        bbox, text, conf = cyrillic_results[i]
        if _is_valid_block(text, conf):
            merged.append((bbox, text, conf))

    # Определяем тип письма по суммарному числу букв в тексте (а не по числу рамок)
    all_text = " ".join(t for _, t, _ in merged)
    cyr_total = sum(1 for ch in all_text if ch in _CYRILLIC_CHARS)
    lat_total = sum(1 for ch in all_text if 'a' <= ch.lower() <= 'z')

    detected_script = "cyrillic" if cyr_total >= lat_total else "latin"
    return merged, detected_script


def _stub_ocr_result(image_path: str) -> dict:
    """Заглушка OCR для тестирования без EasyOCR (CI, unit-тесты)."""
    time.sleep(1)
    filename = Path(image_path).name
    return {
        "raw_text":       f"[STUB] Текст из файла: {filename}",
        "corrected_text": f"[STUB] Исправленный текст из файла: {filename}",
        "converted_text": f"[STUB] Konvertatsiya qilingan matn: {filename}",
        "confidence":     0.95,
        "script":         "latin",
        "blocks_count":   1,
        "lines_count":    1,
        "is_stub":        True,
    }


# ─── Celery Task: OCR-обработка ───────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="ocr_tasks.run_ocr_task",
    max_retries=2,
    default_retry_delay=5,
    throws=(ValueError,),
)
def run_ocr_task(self, image_path: str, output_script: Optional[str] = None) -> dict:
    """
    Основная Celery-задача: OCR-обработка изображения.

    Аргументы:
        image_path (str): Абсолютный путь к временному файлу.
        output_script (str | None): "latin", "cyrillic" или None (auto).

    Возвращает dict: raw_text, corrected_text, converted_text,
    confidence, script, blocks_count, lines_count, processing_time_ms.

    Состояния: PENDING -> PROCESSING -> SUCCESS / FAILURE
    """
    start_time = time.time()
    logger.info(f"[Task {self.request.id}] Starting OCR for: {image_path}")

    self.update_state(
        state="PROCESSING",
        meta={"stage": "loading_image", "progress": 5, "message": "Загрузка изображения..."},
    )

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Временный файл не найден: {image_path}. "
            "Возможно, файл был удалён до начала обработки."
        )

    # FIX #3: try/finally гарантирует удаление temp-файла при любом исходе,
    # в том числе при исключениях на любом этапе пайплайна.
    # Без этого /tmp/uzbek_ocr_uploads/ растёт бесконечно.
    try:
        # ── Шаг 1: Загружаем изображение ─────────────────────────────────
        try:
            with path.open("rb") as f:
                img_bytes = f.read()
            pil_image = Image.open(io.BytesIO(img_bytes))
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            img_array = np.array(pil_image)
            logger.info(
                f"[Task {self.request.id}] Image loaded: "
                f"{pil_image.width}x{pil_image.height}px"
            )
        except Exception as exc:
            logger.error(f"[Task {self.request.id}] Failed to load image: {exc}")
            raise ValueError(f"Не удалось открыть изображение: {exc}") from exc

        # ── Заглушка: EasyOCR недоступен ─────────────────────────────────
        if not EASYOCR_AVAILABLE:
            logger.warning(f"[Task {self.request.id}] Using stub OCR result")
            result = _stub_ocr_result(image_path)
            result["processing_time_ms"] = int((time.time() - start_time) * 1000)
            return result

        # ── Шаг 2: Инициализируем ридеры (singleton) ─────────────────────
        self.update_state(
            state="PROCESSING",
            meta={"stage": "loading_models", "progress": 10, "message": "Инициализация OCR-моделей..."},
        )
        latin_reader, cyrillic_reader = _get_readers()

        # ── Шаг 3: Детекция текстовых регионов (CRAFT) ───────────────────
        self.update_state(
            state="PROCESSING",
            meta={"stage": "text_detection", "progress": 25, "message": "Обнаружение текстовых регионов (CRAFT)..."},
        )
        try:
            from easyocr.utils import reformat_input
            img_normalized, img_grey = reformat_input(img_array)
            del img_array  # FIX #2: освобождаем память после конвертации
            horiz_list, free_list = latin_reader.detect(img_normalized, reformat=False)
            del img_normalized  # FIX #2: больше не нужен
            horiz_list = horiz_list[0] if horiz_list else []
            free_list  = free_list[0]  if free_list  else []
        except Exception as exc:
            logger.error(f"[Task {self.request.id}] CRAFT detection failed: {exc}")
            raise

        # ── Шаг 4: Распознавание двумя ридерами ──────────────────────────
        self.update_state(
            state="PROCESSING",
            meta={"stage": "ocr_recognition", "progress": 50, "message": "Распознавание текста (Dual-Reader)..."},
        )
        if horiz_list or free_list:
            latin_results    = latin_reader.recognize(img_grey, horiz_list, free_list, reformat=False)
            cyrillic_results = cyrillic_reader.recognize(img_grey, horiz_list, free_list, reformat=False)
        else:
            latin_results, cyrillic_results = [], []

        if not latin_results and not cyrillic_results:
            logger.warning(f"[Task {self.request.id}] CRAFT found no regions, fallback to full-image")
            h, w = img_grey.shape[:2]
            fallback_horiz = [[0, w, 0, h]]
            latin_results    = latin_reader.recognize(img_grey, fallback_horiz, [], reformat=False)
            cyrillic_results = cyrillic_reader.recognize(img_grey, fallback_horiz, [], reformat=False)
        del img_grey  # FIX #2: освобождаем память

        # ── Шаг 5: Merge результатов ──────────────────────────────────────
        raw_results, detected_script = _merge_dual_reader_results(latin_results, cyrillic_results)

        if not raw_results:
            logger.info(f"[Task {self.request.id}] No text detected")
            return {
                "raw_text": "", "corrected_text": "", "converted_text": "",
                "confidence": 0.0, "script": "unknown",
                "blocks_count": 0, "lines_count": 0,
                "processing_time_ms": int((time.time() - start_time) * 1000),
                "message": "Текст не обнаружен на изображении.",
            }

        # ── Шаг 6: Нормализация гомоглифов ───────────────────────────────
        self.update_state(
            state="PROCESSING",
            meta={"stage": "normalization", "progress": 70, "message": "Нормализация гомоглифов..."},
        )
        norm = _get_normalizer()
        if norm is not None:
            script_enum = Script.CYRILLIC if detected_script == "cyrillic" else Script.LATIN
            normalized_results = [
                (bbox, norm.normalize(text, script=script_enum), conf)
                for bbox, text, conf in raw_results
            ]
        else:
            normalized_results = raw_results

        if RECONSTRUCTOR_AVAILABLE:
            raw_text = reconstruct_layout(normalized_results)
        else:
            raw_text = "\n".join(t for _, t, _ in normalized_results)

        # ── Шаг 7: Исправление орфографии ────────────────────────────────
        self.update_state(
            state="PROCESSING",
            meta={"stage": "spell_correction", "progress": 85, "message": "Исправление орфографии..."},
        )
        corr = _get_corrector()
        if corr is not None:
            corrected_results = [
                (bbox, corr.correct_text(text, script=detected_script), conf)
                for bbox, text, conf in normalized_results
            ]
        else:
            corrected_results = normalized_results

        if RECONSTRUCTOR_AVAILABLE:
            meta_result    = reconstruct_layout_with_meta(corrected_results)
            corrected_text = meta_result["text"]
            blocks_count   = meta_result["blocks_count"]
            lines_count    = meta_result["lines_count"]
        else:
            corrected_text = "\n".join(t for _, t, _ in corrected_results)
            blocks_count   = len(corrected_results)
            lines_count    = corrected_text.count("\n") + 1

        # ── Шаг 8: Конвертация алфавита ───────────────────────────────────
        self.update_state(
            state="PROCESSING",
            meta={"stage": "script_conversion", "progress": 95, "message": "Конвертация алфавита..."},
        )
        converted_text = _convert_script(corrected_text, detected_script, output_script)

        avg_confidence     = sum(r[2] for r in raw_results) / len(raw_results)
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"[Task {self.request.id}] OCR complete: "
            f"blocks={blocks_count} | conf={avg_confidence:.3f} | "
            f"script={detected_script} | time={processing_time_ms}ms"
        )

        return {
            "raw_text":           raw_text,
            "corrected_text":     corrected_text,
            "converted_text":     converted_text,
            "confidence":         round(avg_confidence, 4),
            "script":             detected_script,
            "blocks_count":       blocks_count,
            "lines_count":        lines_count,
            "processing_time_ms": processing_time_ms,
        }

    finally:
        # FIX #3: гарантированное удаление temp-файла при любом исходе
        try:
            path.unlink(missing_ok=True)
            logger.debug(f"[Task {self.request.id}] Temp file deleted: {image_path}")
        except Exception as del_err:
            logger.warning(f"[Task {self.request.id}] Could not delete temp file: {del_err}")


# ─── Вспомогательная конвертация алфавита ─────────────────────────────────────

_LAT_TO_CYR: list = [
    ("O\u2019", "Ў"), ("o\u2019", "ў"),
    ("G\u2019", "Ғ"), ("g\u2019", "ғ"),
    ("Sh", "Ш"), ("sh", "ш"), ("Ch", "Ч"), ("ch", "ч"),
    ("Ng", "Нг"), ("ng", "нг"), ("SH", "Ш"), ("CH", "Ч"),
    ("A", "А"), ("a", "а"), ("B", "Б"), ("b", "б"),
    ("D", "Д"), ("d", "д"), ("E", "Е"), ("e", "е"),
    ("F", "Ф"), ("f", "ф"), ("G", "Г"), ("g", "г"),
    ("H", "Ҳ"), ("h", "ҳ"), ("I", "И"), ("i", "и"),
    ("J", "Ж"), ("j", "ж"), ("K", "К"), ("k", "к"),
    ("L", "Л"), ("l", "л"), ("M", "М"), ("m", "м"),
    ("N", "Н"), ("n", "н"), ("O", "О"), ("o", "о"),
    ("P", "П"), ("p", "п"), ("Q", "Қ"), ("q", "қ"),
    ("R", "Р"), ("r", "р"), ("S", "С"), ("s", "с"),
    ("T", "Т"), ("t", "т"), ("U", "У"), ("u", "у"),
    ("V", "В"), ("v", "в"), ("X", "Х"), ("x", "х"),
    ("Y", "Й"), ("y", "й"), ("Z", "З"), ("z", "з"),
]

_CYR_TO_LAT: list = [
    ("Ў", "O\u2019"), ("ў", "o\u2019"), ("Қ", "Q"), ("қ", "q"),
    ("Ғ", "G\u2019"), ("ғ", "g\u2019"), ("Ҳ", "H"), ("ҳ", "h"),
    ("Ш", "Sh"), ("ш", "sh"), ("Ч", "Ch"), ("ч", "ch"),
    ("А", "A"), ("а", "a"), ("Б", "B"), ("б", "b"),
    ("В", "V"), ("в", "v"), ("Г", "G"), ("г", "g"),
    ("Д", "D"), ("д", "d"), ("Е", "E"), ("е", "e"),
    ("Ж", "J"), ("ж", "j"), ("З", "Z"), ("з", "z"),
    ("И", "I"), ("и", "i"), ("Й", "Y"), ("й", "y"),
    ("К", "K"), ("к", "k"), ("Л", "L"), ("л", "l"),
    ("М", "M"), ("м", "m"), ("Н", "N"), ("н", "n"),
    ("О", "O"), ("о", "o"), ("П", "P"), ("п", "p"),
    ("Р", "R"), ("р", "r"), ("С", "S"), ("с", "s"),
    ("Т", "T"), ("т", "t"), ("У", "U"), ("у", "u"),
    ("Ф", "F"), ("ф", "f"), ("Х", "X"), ("х", "x"),
    ("Ц", "Ts"), ("ц", "ts"), ("Щ", "Sh"), ("щ", "sh"),
    ("Ъ", ""), ("ъ", ""), ("Ы", "I"), ("ы", "i"),
    ("Ь", ""), ("ь", ""), ("Э", "E"), ("э", "e"),
    ("Ю", "Yu"), ("ю", "yu"), ("Я", "Ya"), ("я", "ya"),
]


def _convert_script(
    text: str,
    detected_script: str,
    output_script: Optional[str],
) -> str:
    """
    Конвертирует текст между алфавитами.

    Логика:
      - output_script="cyrillic" -> всегда в кириллицу
      - output_script="latin"    -> всегда в латиницу
      - output_script=None       -> "зеркальная" конвертация:
          latin -> cyrillic, cyrillic -> latin
    """
    want_cyrillic = (
        output_script == "cyrillic"
        or (output_script is None and detected_script == "latin")
    )
    want_latin = (
        output_script == "latin"
        or (output_script is None and detected_script == "cyrillic")
    )

    result = text
    if want_cyrillic:
        for lat, cyr in _LAT_TO_CYR:
            result = result.replace(lat, cyr)
    elif want_latin:
        for cyr, lat in _CYR_TO_LAT:
            result = result.replace(cyr, lat)
    return result
