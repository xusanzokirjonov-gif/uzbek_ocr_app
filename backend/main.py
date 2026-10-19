"""
main.py
=======
Узбекский OCR — FastAPI Backend
================================
Сервер принимает изображения и возвращает распознанный текст
на узбекском языке (латиница и/или кириллица).

Архитектура v1 (синхронная, POST /ocr):
  ┌─────────────────────────────────────────────────────┐
  │                   FastAPI Server                    │
  │                                                     │
  │  POST /ocr  ──► EasyOCR ──► Normalize ──► Response │
  │             (блокирует поток на 10–60 сек)          │
  └─────────────────────────────────────────────────────┘

Архитектура v2 (асинхронная, POST /ocr/v2 + GET /ocr/status):
  ┌────────────────────────────────────────────────────────────────┐
  │  Клиент                                                        │
  │    │ POST /ocr/v2  → FastAPI сохраняет файл во tmp             │
  │    │               → .delay() → Redis (брокер) → Celery Worker │
  │    │               ← {task_id, status: PENDING} (мгновенно)    │
  │    │                                                            │
  │    │ GET /ocr/status/{task_id}  (polling или long-poll)        │
  │    │  ← {status: PROCESSING, progress: 50}                     │
  │    │  ← {status: SUCCESS, result: {...}}  (когда готово)       │
  └────────────────────────────────────────────────────────────────┘

Стратегия двойного ридера (Dual-Reader Strategy):
  Для максимального покрытия латиницы и кириллицы используем
  два EasyOCR-ридера. Детекция текстовых регионов (CRAFT)
  выполняется один раз, а распознавание — двумя ридерами.
  Для каждого блока выбирается тот результат, который содержит
  больше символов целевого алфавита.
"""

import asyncio
import functools
import io
import os
import time
import uuid
import socket
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Literal

import numpy as np
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import easyocr
from celery.result import AsyncResult

# mDNS / Zero-Configuration Networking
from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

from homoglyph_normalizer import HomoglyphNormalizer, Script, detect_script
from spelling_corrector import UzbekSpellingCorrector
from layout_reconstructor import reconstruct_layout, reconstruct_layout_with_meta
from celery_app import celery_app           # Celery-приложение (брокер + backend)
from ocr_tasks import run_ocr_task          # Фоновая задача OCR

# ─── Логирование ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("uzbek_ocr")

# ─── Пути к ресурсам ──────────────────────────────────────────────────────────

BASE_DIR        = Path(__file__).resolve().parent
MODEL_DIR       = BASE_DIR / "model"
DICT_PATH       = MODEL_DIR / "uzwords.txt"
LATIN_DICT_PATH = MODEL_DIR / "uzwords_latin.txt"

# ─── Глобальные компоненты ────────────────────────────────────────────────────
# Инициализируются при запуске сервера (lifespan), переиспользуются для
# всех запросов. EasyOCR загрузка занимает ~30–60 сек при первом запуске.

latin_reader:    Optional[easyocr.Reader]          = None
cyrillic_reader: Optional[easyocr.Reader]          = None
normalizer:      Optional[HomoglyphNormalizer]      = None
corrector:       Optional[UzbekSpellingCorrector]   = None

# mDNS-объекты (создаются в lifespan, используются при завершении работы)
_zeroconf:      Optional[AsyncZeroconf]  = None
_mdns_service:  Optional[ServiceInfo]   = None


# ─── mDNS вспомогательная функция ────────────────────────────────────────────

def get_local_ip() -> str:
    """
    Определяет текущий локальный IP-адрес машины в локальной сети.

    Метод использует временное UDP-соединение к публичному DNS-серверу
    Google (8.8.8.8) — пакеты реально НЕ отправляются. Это стандартный
    трюк для надёжного определения исходящего IP без разбора сетевых
    интерфейсов вручную.

    Returns:
        str: IP-адрес в формате "192.168.x.x" или "127.0.0.1" как fallback.
    """
    try:
        # Создаём UDP-сокет и «подключаемся» к внешнему адресу.
        # connect() на UDP только устанавливает адрес назначения по умолчанию,
        # реальной передачи данных не происходит.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
        sock.close()
        return local_ip
    except OSError:
        # Если сеть недоступна — возвращаем loopback
        return "127.0.0.1"


# ─── Константы mDNS ───────────────────────────────────────────────────────────

# Имя сервиса в локальной сети. После регистрации сервер будет доступен
# по адресу http://uzbek-ocr.local:8000 на всех устройствах в сети.
MDNS_SERVICE_NAME = "uzbek-ocr"        # Имя экземпляра сервиса
MDNS_SERVICE_TYPE = "_http._tcp.local."  # Стандартный тип для HTTP (RFC 6335)
MDNS_PORT         = 8000               # Порт FastAPI-сервера


# ─── Запуск и остановка сервера ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Менеджер жизненного цикла сервера (AsyncContextManager).

    Инициализирует все компоненты при запуске и освобождает ресурсы
    при остановке (для корректного завершения работы в Docker).

    Порядок инициализации:
        1. EasyOCR ридеры (латиница + кириллица)
        2. Нормализатор омоглифов
        3. Корректор орфографии
        4. mDNS-сервис (регистрация в локальной сети)
    """
    global latin_reader, cyrillic_reader, normalizer, corrector
    global _zeroconf, _mdns_service

    logger.info("=" * 60)
    logger.info("  UZBEK OCR SERVER — Dual-Reader Strategy")
    logger.info(f"  Models dir: {MODEL_DIR}")
    logger.info("=" * 60)

    # ── Инициализация EasyOCR ─────────────────────────────────────────────
    # Латинский ридер: узбекский (uz) + английский (en) для цифр/спецсимволов
    logger.info("Loading Latin EasyOCR reader [uz, en]...")
    latin_reader = easyocr.Reader(
        lang_list=["uz", "en"],
        gpu=False,                    # CPU-режим (без CUDA)
        model_storage_directory=str(MODEL_DIR),
        verbose=False,
        quantize=False,               # FIX: отключение квантования предотвращает обнуление выходов на CPU
    )

    # Кириллический ридер: русский (ru) + белорусский (be) + таджикский (tjk) + английский (en)
    logger.info("Loading Cyrillic EasyOCR reader [ru, be, tjk, en]...")
    cyrillic_reader = easyocr.Reader(
        lang_list=["ru", "be", "tjk", "en"],
        gpu=False,
        model_storage_directory=str(MODEL_DIR),
        verbose=False,
        quantize=False,               # FIX: отключение квантования предотвращает обнуление выходов на CPU
    )

    # ── Инициализация нормализатора ───────────────────────────────────────
    normalizer = HomoglyphNormalizer(prefer_standard_apostrophe=True)
    logger.info("Homoglyph Normalizer initialized.")

    # ── Инициализация исправителя орфографии ──────────────────────────────
    corrector = UzbekSpellingCorrector(
        dict_path=DICT_PATH,
        max_distance=1.5,
        latin_dict_path=LATIN_DICT_PATH if LATIN_DICT_PATH.exists() else None,
    )
    logger.info("Spelling Corrector initialized.")

    # ── Регистрация mDNS-сервиса ──────────────────────────────────────────
    #
    # Zeroconf (RFC 6762) — протокол обнаружения сервисов в локальной сети
    # без центрального DNS-сервера. После регистрации любое устройство в
    # той же Wi-Fi-сети может обратиться к серверу по имени:
    #
    #   http://uzbek-ocr.local:8000
    #
    # вместо изменяющегося IP-адреса (например, 192.168.1.105:8000).
    # На iOS/macOS это работает через Bonjour, на Android — через nsd.
    try:
        server_ip = get_local_ip()
        logger.info(f"Detected local IP address: {server_ip}")

        # ServiceInfo описывает сервис для публикации в mDNS.
        # Параметры:
        #   type_          — тип сервиса по DNS-SD (service discovery)
        #   name           — уникальное имя экземпляра (instance name)
        #   addresses      — список IP-адресов в бинарном формате (4 байта для IPv4)
        #   port           — TCP-порт сервиса
        #   properties     — произвольные TXT-записи (метаданные сервиса)
        #   server         — FQDN хоста (Fully Qualified Domain Name)
        _mdns_service = ServiceInfo(
            type_=MDNS_SERVICE_TYPE,
            name=f"{MDNS_SERVICE_NAME}.{MDNS_SERVICE_TYPE}",
            addresses=[socket.inet_aton(server_ip)],   # IPv4 → 4 байта
            port=MDNS_PORT,
            properties={
                # TXT-записи: дополнительные метаданные сервиса.
                # Читаются клиентом после обнаружения сервиса.
                b"version": b"2.0.0",
                b"lang":    b"uz,ru",
                b"docs":    b"/docs",
            },
            server=f"{MDNS_SERVICE_NAME}.local.",  # Точка в конце обязательна (FQDN)
        )

        # AsyncZeroconf использует уже существующий event loop FastAPI,
        # без создания нового. Это исключает конфликт двух event loop-ов.
        # allow_name_change=True: если имя уже занято, автоматически
        # добавляется числовой суффикс (например, "uzbek-ocr (2)").
        _zeroconf = AsyncZeroconf()
        await _zeroconf.async_register_service(_mdns_service, allow_name_change=True)

        logger.info(
            f"✅ mDNS registered: http://{MDNS_SERVICE_NAME}.local:{MDNS_PORT} "
            f"→ {server_ip}:{MDNS_PORT}"
        )
    except Exception as exc:
        # mDNS — вспомогательная функция; сервер продолжает работу
        # даже если регистрация не удалась (например, в Docker без host-сети).
        logger.warning(f"⚠️  mDNS registration failed (non-fatal): {exc}")

    logger.info("✅ All components ready. Server is accepting requests.")

    yield  # ← Сервер работает. Код ниже выполняется при остановке.

    # ── Завершение работы ─────────────────────────────────────────────────
    logger.info("Shutting down Uzbek OCR server...")

    # Корректно снимаем mDNS-сервис, чтобы другие устройства в сети
    # сразу узнали о его недоступности (Goodbye-пакет по RFC 6762).
    if _zeroconf is not None and _mdns_service is not None:
        try:
            await _zeroconf.async_unregister_service(_mdns_service)
            await _zeroconf.async_close()
            logger.info("mDNS service unregistered and Zeroconf closed.")
        except Exception as exc:
            logger.warning(f"Error during mDNS cleanup: {exc}")


# ─── Создание приложения ──────────────────────────────────────────────────────

app = FastAPI(
    title="Uzbek OCR API",
    description=(
        "REST API для оптического распознавания текста на узбекском языке. "
        "Поддерживает латинский (O'zbek) и кириллический (Ўзбек) алфавиты."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS: разрешаем запросы из Flutter-приложения
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # В продакшене заменить на конкретный домен
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── Health-check эндпоинт ────────────────────────────────────────────────────

@app.get("/", tags=["System"], summary="Статус сервера")
async def root() -> dict:
    """
    Проверка работоспособности сервера (health-check).

    Возвращает базовую информацию о состоянии сервиса.
    Используется мобильным приложением для проверки соединения
    при старте и Flutter-тестами для верификации доступности API.

    Пример запроса:
        GET http://uzbek-ocr.local:8000/

    Пример ответа:
        {
          "status": "ok",
          "service": "Uzbek OCR API",
          "version": "2.0.0",
          "mdns": "uzbek-ocr.local",
          "docs": "/docs"
        }
    """
    return {
        "status":  "ok",
        "service": "Uzbek OCR API",
        "version": "2.0.0",
        "mdns":    f"{MDNS_SERVICE_NAME}.local",
        "docs":    "/docs",
    }


# ─── Конвертер скриптов ───────────────────────────────────────────────────────

class UzbekScriptConverter:
    """
    Конвертер между латинским и кириллическим алфавитами узбекского языка.

    Таблицы транслитерации соответствуют официальному стандарту
    Узбекистана: латиница — UzLat (1995), кириллица — UzCyr.
    """

    # Латиница → кириллица
    _LAT_TO_CYR: list[tuple[str, str]] = [
        # Сначала двухбуквенные комбинации (порядок важен!)
        ("O\u2019", "Ў"),  ("o\u2019", "ў"),
        ("G\u2019", "Ғ"),  ("g\u2019", "ғ"),
        ("Sh",      "Ш"),  ("sh",      "ш"),
        ("Ch",      "Ч"),  ("ch",      "ч"),
        ("Ng",      "Нг"), ("ng",      "нг"),
        ("SH",      "Ш"),  ("CH",      "Ч"),
        # Однобуквенные
        ("A", "А"), ("a", "а"),
        ("B", "Б"), ("b", "б"),
        ("D", "Д"), ("d", "д"),
        ("E", "Е"), ("e", "е"),
        ("F", "Ф"), ("f", "ф"),
        ("G", "Г"), ("g", "г"),
        ("H", "Ҳ"), ("h", "ҳ"),
        ("I", "И"), ("i", "и"),
        ("J", "Ж"), ("j", "ж"),
        ("K", "К"), ("k", "к"),
        ("L", "Л"), ("l", "л"),
        ("M", "М"), ("m", "м"),
        ("N", "Н"), ("n", "н"),
        ("O", "О"), ("o", "о"),
        ("P", "П"), ("p", "п"),
        ("Q", "Қ"), ("q", "қ"),
        ("R", "Р"), ("r", "р"),
        ("S", "С"), ("s", "с"),
        ("T", "Т"), ("t", "т"),
        ("U", "У"), ("u", "у"),
        ("V", "В"), ("v", "в"),
        ("X", "Х"), ("x", "х"),
        ("Y", "Й"), ("y", "й"),
        ("Z", "З"), ("z", "з"),
    ]

    # Кириллица → латиница
    _CYR_TO_LAT: list[tuple[str, str]] = [
        ("Ў",  "O\u2019"), ("ў",  "o\u2019"),
        ("Қ",  "Q"),       ("қ",  "q"),
        ("Ғ",  "G\u2019"), ("ғ",  "g\u2019"),
        ("Ҳ",  "H"),       ("ҳ",  "h"),
        ("Ш",  "Sh"),      ("ш",  "sh"),
        ("Ч",  "Ch"),      ("ч",  "ch"),
        ("А",  "A"),       ("а",  "a"),
        ("Б",  "B"),       ("б",  "b"),
        ("В",  "V"),       ("в",  "v"),
        ("Г",  "G"),       ("г",  "g"),
        ("Д",  "D"),       ("д",  "d"),
        ("Е",  "E"),       ("е",  "e"),
        ("Ж",  "J"),       ("ж",  "j"),
        ("З",  "Z"),       ("з",  "z"),
        ("И",  "I"),       ("и",  "i"),
        ("Й",  "Y"),       ("й",  "y"),
        ("К",  "K"),       ("к",  "k"),
        ("Л",  "L"),       ("л",  "l"),
        ("М",  "M"),       ("м",  "m"),
        ("Н",  "N"),       ("н",  "n"),
        ("О",  "O"),       ("о",  "o"),
        ("П",  "P"),       ("п",  "p"),
        ("Р",  "R"),       ("р",  "r"),
        ("С",  "S"),       ("с",  "s"),
        ("Т",  "T"),       ("т",  "t"),
        ("У",  "U"),       ("у",  "u"),
        ("Ф",  "F"),       ("ф",  "f"),
        ("Х",  "X"),       ("х",  "x"),
        ("Ц",  "Ts"),      ("ц",  "ts"),
        ("Щ",  "Sh"),      ("щ",  "sh"),
        ("Ъ",  ""),        ("ъ",  ""),
        ("Ы",  "I"),       ("ы",  "i"),
        ("Ь",  ""),        ("ь",  ""),
        ("Э",  "E"),       ("э",  "e"),
        ("Ю",  "Yu"),      ("ю",  "yu"),
        ("Я",  "Ya"),      ("я",  "ya"),
    ]

    @classmethod
    def to_cyrillic(cls, text: str) -> str:
        """Конвертирует латинский текст в кириллицу."""
        result = text
        for lat, cyr in cls._LAT_TO_CYR:
            result = result.replace(lat, cyr)
        return result

    @classmethod
    def to_latin(cls, text: str) -> str:
        """Конвертирует кириллический текст в латиницу."""
        result = text
        for cyr, lat in cls._CYR_TO_LAT:
            result = result.replace(cyr, lat)
        return result

    @classmethod
    def auto_convert(cls, text: str) -> str:
        """Автоматически определяет тип письма и конвертирует в обратный."""
        script = detect_script(text)
        if script == Script.CYRILLIC:
            return cls.to_latin(text)
        return cls.to_cyrillic(text)


# ─── Валидатор изображений ────────────────────────────────────────────────────

# Поддерживаемые MIME-типы изображений
ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/bmp", "image/tiff", "image/webp",
    "application/octet-stream",  # iOS иногда отправляет без MIME
}

MAX_IMAGE_SIZE_MB = 20
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024


def validate_image(file: UploadFile, contents: bytes) -> None:
    """
    Проверяет загруженный файл на соответствие требованиям.

    Args:
        file: Метаданные файла от FastAPI.
        contents: Содержимое файла в байтах.

    Raises:
        HTTPException 400: Если файл не является изображением или слишком большой.
        HTTPException 422: Если файл пустой.
    """
    # Проверка на пустой файл
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файл пустой (0 байт). Пожалуйста, выберите другое изображение.",
        )

    # Проверка размера
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл слишком большой: {len(contents) // 1024 // 1024} МБ. "
                   f"Максимум: {MAX_IMAGE_SIZE_MB} МБ.",
        )

    # Проверка MIME-типа
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый формат файла: {content_type}. "
                   f"Поддерживаются: JPEG, PNG, BMP, TIFF, WebP.",
        )

    # Проверка магического числа (первые байты файла)
    # Это надёжнее, чем проверка MIME-типа от клиента
    magic_signatures = {
        b"\xff\xd8\xff": "JPEG",
        b"\x89PNG": "PNG",
        b"BM": "BMP",
        b"II\x2a\x00": "TIFF",
        b"MM\x00\x2a": "TIFF",
        b"RIFF": "WebP",
    }
    is_valid_image = any(contents.startswith(sig) for sig in magic_signatures)
    if not is_valid_image:
        logger.warning(f"Unknown magic bytes: {contents[:8].hex()}")
        # Не отклоняем — PIL сам проверит при открытии


# ─── Обработка OCR-результатов ────────────────────────────────────────────────

_CYRILLIC_CHARS = set(
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


def merge_dual_reader_results(
    latin_results: list,
    cyrillic_results: list,
) -> tuple[list, str]:
    """
    Объединяет результаты двух EasyOCR-ридеров, выбирая лучший для каждого блока.
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

    # Определяем общий тип письма документа по реальному числу символов
    all_text = " ".join(t for _, t, _ in merged)
    cyr_total = sum(1 for ch in all_text if ch in _CYRILLIC_CHARS)
    lat_total = sum(1 for ch in all_text if 'a' <= ch.lower() <= 'z')

    detected_script = "cyrillic" if cyr_total >= lat_total else "latin"

    return merged, detected_script


# ─── Эндпоинты ────────────────────────────────────────────────────────────────

@app.get("/", summary="Health check")
async def root():
    """Быстрая проверка доступности сервера."""
    return {
        "service": "Uzbek OCR API",
        "version": "2.0.0",
        "status": "running",
        "supported_scripts": ["Latin (O'zbek)", "Cyrillic (Ўзбек)"],
        "endpoints": {
            # ── v1: синхронный эндпоинт (блокирующий) ────────────────────
            "ocr_sync":   "POST /ocr",
            # ── v2: асинхронный эндпоинт (Celery + Redis) ────────────────
            "ocr_async":  "POST /ocr/v2",
            "ocr_status": "GET /ocr/status/{task_id}",
            # ── служебные ────────────────────────────────────────────────
            "health":     "GET /health",
            "docs":       "GET /docs",
        },
    }


@app.get("/health", summary="Detailed health check")
async def health_check():
    """Подробная проверка состояния всех компонентов."""
    return {
        "status": "healthy",
        "components": {
            "latin_reader":    latin_reader    is not None,
            "cyrillic_reader": cyrillic_reader is not None,
            "normalizer":      normalizer      is not None,
            "corrector":       corrector       is not None,
        },
        "configuration": {
            "ocr_engine":      "EasyOCR (Dual-Reader)",
            "gpu_enabled":     False,
            "languages":       ["uz", "ru", "be", "tjk", "en"],
            "dict_loaded":     bool(corrector and (corrector._cyrillic_words or corrector._latin_words)),
            "dict_cyrillic":   len(corrector._cyrillic_words) if corrector else 0,
            "dict_latin":      len(corrector._latin_words)    if corrector else 0,
        },
    }


@app.post(
    "/ocr",
    summary="Recognize text from image",
    response_description="Recognized Uzbek text with metadata",
)
async def recognize_text(image: UploadFile = File(..., description="Image file (JPEG/PNG/BMP/TIFF)")):
    """
    Распознаёт узбекский текст на изображении.

    **Процесс обработки:**
    1. Валидация изображения (формат, размер).
    2. Детекция текстовых регионов (CRAFT detector).
    3. Распознавание двумя ридерами (латинский + кириллический).
    4. Выбор лучшего результата для каждого блока.
    5. Нормализация гомоглифов.
    6. Исправление орфографии.
    7. Реконструкция разметки.
    8. Конвертация между алфавитами.

    **Входные данные:**
    - `image`: Изображение в формате multipart/form-data.

    **Возвращает:**
    JSON с распознанным текстом и метаданными.
    """
    start_time = time.time()
    logger.info(f"Received: '{image.filename}' | type: {image.content_type}")

    # ── Шаг 1: Читаем и валидируем изображение ────────────────────────────
    contents = await image.read()
    validate_image(image, contents)

    logger.info(f"Image size: {len(contents)} bytes | magic: {contents[:4].hex()}")

    try:
        # ── Шаг 2: Преобразуем в numpy array для EasyOCR ──────────────────
        pil_image = Image.open(io.BytesIO(contents))

        # EasyOCR требует RGB (без альфа-канала)
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        img_array = np.array(pil_image)
        logger.info(f"Image shape: {img_array.shape} ({pil_image.width}×{pil_image.height}px)")

        # ── Шаг 3: Детекция текстовых регионов (один раз для обоих ридеров)
        # FIX #1: EasyOCR — синхронная CPU-bound библиотека. Вызываем через
        # run_in_executor чтобы не блокировать asyncio event loop FastAPI.
        # Без этого один OCR-запрос блокирует ВЕСЬ сервер на 10–60 сек.
        loop = asyncio.get_event_loop()

        from easyocr.utils import reformat_input
        img_normalized, img_grey = await loop.run_in_executor(
            None, reformat_input, img_array
        )

        detect_fn = functools.partial(latin_reader.detect, img_normalized, reformat=False)
        horiz_list_raw, free_list_raw = await loop.run_in_executor(None, detect_fn)
        horiz_list = horiz_list_raw[0] if horiz_list_raw else []
        free_list  = free_list_raw[0]  if free_list_raw  else []

        # FIX #2: освобождаем исходный numpy-массив как только он больше не нужен
        del img_array

        # ── Шаг 4: Распознавание двумя ридерами (не блокируем event loop) ──
        if horiz_list or free_list:
            latin_fn    = functools.partial(latin_reader.recognize,    img_grey, horiz_list, free_list, reformat=False)
            cyrillic_fn = functools.partial(cyrillic_reader.recognize, img_grey, horiz_list, free_list, reformat=False)
            latin_results    = await loop.run_in_executor(None, latin_fn)
            cyrillic_results = await loop.run_in_executor(None, cyrillic_fn)
        else:
            latin_results, cyrillic_results = [], []

        # Fallback: если CRAFT не нашёл блоков — распознаём всё изображение целиком
        if not latin_results and not cyrillic_results:
            logger.warning("CRAFT found no text regions. Falling back to full-image recognition.")
            h, w = img_grey.shape[:2]
            fallback_horiz = [[0, w, 0, h]]
            latin_fn    = functools.partial(latin_reader.recognize,    img_grey, fallback_horiz, [], reformat=False)
            cyrillic_fn = functools.partial(cyrillic_reader.recognize, img_grey, fallback_horiz, [], reformat=False)
            latin_results    = await loop.run_in_executor(None, latin_fn)
            cyrillic_results = await loop.run_in_executor(None, cyrillic_fn)

        # FIX #2: освобождаем промежуточные данные
        del img_grey, img_normalized

        # ── Шаг 5: Объединяем результаты двух ридеров ────────────────────
        raw_results, detected_script = merge_dual_reader_results(
            latin_results, cyrillic_results
        )

        if not raw_results:
            return JSONResponse({
                "success": True,
                "raw_text": "",
                "corrected_text": "",
                "converted_text": "",
                "confidence": 0.0,
                "script": "unknown",
                "blocks_count": 0,
                "processing_time_ms": int((time.time() - start_time) * 1000),
                "message": "Текст не обнаружен на изображении.",
            })

        script_enum = Script.CYRILLIC if detected_script == "cyrillic" else Script.LATIN

        # ── Шаг 6: Нормализация гомоглифов (raw результаты) ─────────────
        normalized_results = []
        for bbox, text, conf in raw_results:
            clean_text = normalizer.normalize(text, script=script_enum)
            normalized_results.append((bbox, clean_text, conf))

        # ── Шаг 7: Реконструкция разметки (сырой текст) ──────────────────
        raw_text = reconstruct_layout(normalized_results)

        # ── Шаг 8: Исправление орфографии ────────────────────────────────
        corrected_results = []
        for bbox, text, conf in normalized_results:
            corrected = corrector.correct_text(text, script=detected_script)
            corrected_results.append((bbox, corrected, conf))

        # Реконструкция разметки исправленного текста
        meta = reconstruct_layout_with_meta(corrected_results)
        corrected_text = meta["text"]

        # ── Шаг 9: Конвертация между алфавитами ──────────────────────────
        converted_text = UzbekScriptConverter.auto_convert(corrected_text)

        # ── Итоговые метрики ──────────────────────────────────────────────
        avg_confidence = (
            sum(r[2] for r in raw_results) / len(raw_results)
            if raw_results else 0.0
        )
        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"Done: {len(raw_results)} blocks | "
            f"conf={avg_confidence:.2f} | "
            f"script={detected_script} | "
            f"time={processing_time_ms}ms"
        )
        logger.debug(f"Raw:       {raw_text[:200]!r}")
        logger.debug(f"Corrected: {corrected_text[:200]!r}")

        return JSONResponse({
            "success":          True,
            "raw_text":         raw_text,
            "corrected_text":   corrected_text,
            "converted_text":   converted_text,
            "confidence":       round(avg_confidence, 4),
            "script":           detected_script,
            "blocks_count":     meta["blocks_count"],
            "lines_count":      meta["lines_count"],
            "processing_time_ms": processing_time_ms,
        })

    except HTTPException:
        raise  # Пробрасываем наши ошибки валидации

    except Exception as exc:
        logger.exception(f"OCR processing error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обработке изображения: {str(exc)}",
        )


# ─── Pydantic-схемы для v2 эндпоинтов ───────────────────────────────────────
#
# Явные схемы вместо dict улучшают автодокументацию Swagger UI
# и упрощают валидацию на стороне клиента.

class OcrSubmitResponse(BaseModel):
    """
    Ответ на POST /ocr/v2.

    Возвращается мгновенно после постановки задачи в очередь.
    Клиент использует task_id для последующего опроса статуса.
    """
    task_id: str = Field(
        ...,
        description="Уникальный идентификатор задачи Celery (UUID4)",
        example="3fa85f64-5717-4562-b3fc-2c963f66afa6",
    )
    status: Literal["PENDING"] = Field(
        default="PENDING",
        description="Начальный статус задачи",
    )
    message: str = Field(
        default="Задача поставлена в очередь. Используйте task_id для проверки статуса.",
        description="Информационное сообщение",
    )
    poll_url: str = Field(
        ...,
        description="URL для проверки статуса задачи",
        example="/ocr/status/3fa85f64-5717-4562-b3fc-2c963f66afa6",
    )


class OcrStatusResponse(BaseModel):
    """
    Ответ на GET /ocr/status/{task_id}.

    Поле result заполняется только при status=SUCCESS.
    При status=PROCESSING возвращается прогресс выполнения.
    """
    task_id: str = Field(..., description="Идентификатор задачи")
    status: str = Field(
        ...,
        description="Статус задачи: PENDING | PROCESSING | SUCCESS | FAILURE",
    )
    # Прогресс (только при status=PROCESSING)
    progress: Optional[int] = Field(
        default=None,
        description="Прогресс выполнения от 0 до 100 (при status=PROCESSING)",
        ge=0, le=100,
    )
    stage: Optional[str] = Field(
        default=None,
        description="Текущий этап обработки (при status=PROCESSING)",
    )
    message: Optional[str] = Field(
        default=None,
        description="Текстовое описание текущего состояния",
    )
    # Результат (только при status=SUCCESS)
    result: Optional[dict] = Field(
        default=None,
        description="Результат OCR-обработки (при status=SUCCESS)",
    )
    # Информация об ошибке (только при status=FAILURE)
    error: Optional[str] = Field(
        default=None,
        description="Описание ошибки (при status=FAILURE)",
    )


# ─── Эндпоинты v2: асинхронная OCR-обработка ─────────────────────────────────

# FIX #12: TEMP_UPLOAD_DIR читается из переменной окружения OCR_UPLOAD_DIR.
# В Docker Compose api и worker — разные контейнеры с разными ФС.
# Монтируем общий volume и указываем один путь для обоих:
#
#   environment:
#     - OCR_UPLOAD_DIR=/uploads
#   volumes:
#     - ocr_uploads:/uploads
#
# Для локального запуска без Docker переменная не нужна:
# по умолчанию используется /tmp/uzbek_ocr_uploads.
TEMP_UPLOAD_DIR = Path(
    os.environ.get("OCR_UPLOAD_DIR", "") or tempfile.gettempdir()
) / "uzbek_ocr_uploads"
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Temp upload dir: {TEMP_UPLOAD_DIR}")


@app.post(
    "/ocr/v2",
    response_model=OcrSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,   # 202 Accepted — задача принята, не завершена
    summary="[Async] Submit image for OCR processing",
    description=(
        "Асинхронный вариант OCR. "
        "Принимает изображение, сохраняет во временный файл и ставит задачу "
        "в очередь Celery. Возвращает task_id мгновенно. "
        "Используйте GET /ocr/status/{task_id} для получения результата."
    ),
    tags=["OCR v2 (Async)"],
)
async def submit_ocr_task(
    image: UploadFile = File(
        ...,
        description="Изображение в формате JPEG/PNG/BMP/TIFF/WebP",
    ),
    output_script: Optional[Literal["latin", "cyrillic"]] = Query(
        default=None,
        description="Желаемый алфавит вывода. None = авто-конвертация.",
    ),
) -> OcrSubmitResponse:
    """
    Принимает изображение и ставит OCR-задачу в очередь Celery.

    **Процесс (v2):**
    1. Валидация загруженного файла.
    2. Сохранение файла во временную директорию.
    3. Постановка задачи `run_ocr_task` в очередь через `.delay()`.
    4. Мгновенный возврат JSON с `task_id` и статусом `PENDING`.

    **Почему 202 Accepted?**
    HTTP 202 семантически означает «запрос принят, обработка ещё не завершена».
    Это стандарт для асинхронных API (RFC 7231).

    **Опрос результата:**
    Используйте `GET /ocr/status/{task_id}` для получения статуса и результата.
    Рекомендуемый интервал опроса: 1–3 секунды.
    """
    # ── Шаг 1: Читаем и валидируем файл ──────────────────────────────────────
    contents = await image.read()
    validate_image(image, contents)  # Переиспользуем существующий валидатор

    logger.info(
        f"[v2] Received: '{image.filename}' | "
        f"size={len(contents)} bytes | type={image.content_type}"
    )

    # ── Шаг 2: Сохраняем файл во временную директорию ────────────────────────
    #
    # Используем UUID4 как имя файла: это гарантирует уникальность
    # и исключает коллизии при параллельных запросах.
    # Расширение сохраняем для PIL (некоторые форматы определяются по ext).
    original_suffix = Path(image.filename or "image.jpg").suffix or ".jpg"
    temp_filename = f"{uuid.uuid4()}{original_suffix}"
    temp_path = TEMP_UPLOAD_DIR / temp_filename

    try:
        temp_path.write_bytes(contents)
        logger.info(f"[v2] Saved temp file: {temp_path}")
    except OSError as exc:
        logger.error(f"[v2] Failed to save temp file: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось сохранить файл для обработки: {exc}",
        )

    # ── Шаг 3: Ставим задачу в очередь Celery ────────────────────────────────
    #
    # .delay(*args, **kwargs) — сокращение для .apply_async(args, kwargs).
    # Метод НЕ ЖДЁТ выполнения задачи, а только публикует сообщение в Redis.
    # Возвращает AsyncResult с task_id.
    #
    # Передаём строковый путь (не Path), т.к. Celery сериализует аргументы в JSON.
    try:
        task: AsyncResult = run_ocr_task.delay(
            str(temp_path),
            output_script,
        )
        logger.info(
            f"[v2] Task submitted: id={task.id} | file={temp_filename}"
        )
    except Exception as exc:
        # Если Redis недоступен — удаляем временный файл и возвращаем ошибку
        temp_path.unlink(missing_ok=True)
        logger.error(f"[v2] Failed to submit Celery task: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Очередь задач недоступна: {exc}. "
                "Проверьте, что Redis запущен и доступен."
            ),
        )

    # ── Шаг 4: Мгновенно возвращаем task_id клиенту ──────────────────────────
    return OcrSubmitResponse(
        task_id=task.id,
        poll_url=f"/ocr/status/{task.id}",
    )


@app.get(
    "/ocr/status/{task_id}",
    response_model=OcrStatusResponse,
    summary="[Async] Get OCR task status and result",
    description=(
        "Проверяет состояние асинхронной OCR-задачи. "
        "Возвращает прогресс при status=PROCESSING "
        "или итоговый текст при status=SUCCESS."
    ),
    tags=["OCR v2 (Async)"],
)
async def get_ocr_status(task_id: str) -> OcrStatusResponse:
    """
    Возвращает текущий статус OCR-задачи.

    **Жизненный цикл задачи:**
    ```
    PENDING → PROCESSING → SUCCESS
                        ↘ FAILURE
    ```

    **Состояния:**
    - `PENDING`    — задача в очереди (ещё не взята воркером или TTL истёк)
    - `PROCESSING` — воркер выполняет OCR (возвращается прогресс 0–100)
    - `SUCCESS`    — задача завершена, результат в поле `result`
    - `FAILURE`    — произошла ошибка, описание в поле `error`

    **Рекомендации по опросу:**
    Опрашивайте с интервалом 1–3 секунды.
    При получении SUCCESS или FAILURE — прекратите опрос.

    **Примечание о TTL:**
    Результаты хранятся в Redis 1 час.
    После истечения TTL статус снова станет PENDING.
    """
    # ── Получаем AsyncResult из Redis ────────────────────────────────────────
    #
    # AsyncResult не делает сетевой запрос при создании объекта.
    # Сетевой запрос происходит только при обращении к .state/.result/.info.
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        task_state  = task_result.state    # Обращение к Redis
    except Exception as exc:
        logger.error(f"[status] Redis connection error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Не удалось подключиться к Redis для проверки статуса: {exc}",
        )

    logger.debug(f"[status] Task {task_id}: state={task_state}")

    # ── Обрабатываем каждое состояние задачи ─────────────────────────────────

    if task_state == "PENDING":
        # Задача ещё не взята воркером (или TTL истёк)
        return OcrStatusResponse(
            task_id=task_id,
            status="PENDING",
            message="Задача ожидает обработки в очереди...",
        )

    elif task_state == "PROCESSING":
        # Кастомное состояние: воркер опубликовал промежуточный прогресс
        # через self.update_state(state='PROCESSING', meta={...})
        meta = task_result.info or {}
        return OcrStatusResponse(
            task_id=task_id,
            status="PROCESSING",
            progress=meta.get("progress"),
            stage=meta.get("stage"),
            message=meta.get("message", "Обработка изображения..."),
        )

    elif task_state == "STARTED":
        # Стандартное Celery-состояние (task_track_started=True)
        return OcrStatusResponse(
            task_id=task_id,
            status="PROCESSING",
            progress=0,
            stage="started",
            message="Воркер начал обработку задачи...",
        )

    elif task_state == "SUCCESS":
        # Задача успешно завершена: возвращаем результат OCR
        result_data = task_result.result  # dict из ocr_tasks.run_ocr_task
        return OcrStatusResponse(
            task_id=task_id,
            status="SUCCESS",
            progress=100,
            message="Распознавание завершено успешно.",
            result=result_data,
        )

    elif task_state == "FAILURE":
        # Задача завершилась с ошибкой
        # task_result.result содержит объект исключения
        exc = task_result.result
        error_msg = str(exc) if exc else "Неизвестная ошибка при обработке."
        logger.warning(f"[status] Task {task_id} FAILED: {error_msg}")
        return OcrStatusResponse(
            task_id=task_id,
            status="FAILURE",
            error=error_msg,
            message="Задача завершилась с ошибкой.",
        )

    elif task_state == "REVOKED":
        # Задача была отменена вручную (например, через celery.control.revoke)
        return OcrStatusResponse(
            task_id=task_id,
            status="FAILURE",
            error="Задача была отменена.",
        )

    else:
        # Неизвестное состояние (нестандартное или промежуточное)
        return OcrStatusResponse(
            task_id=task_id,
            status=task_state,
            message=f"Промежуточное состояние: {task_state}",
        )


# ─── Точка входа (для локального запуска) ─────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,       # Reload отключён (несовместим с EasyOCR в памяти)
        log_level="info",
        access_log=True,
    )
