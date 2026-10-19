# ─── Uzbek OCR Backend — Dockerfile ──────────────────────────────────────────
#
# Многоэтапная сборка (multi-stage build) для минимизации размера образа.
#
# Этапы:
#   builder  — устанавливает зависимости в виртуальное окружение
#   runtime  — копирует только нужные файлы, без build-инструментов
#
# Целевая платформа: linux/amd64 (x86-64)
# Базовый образ: python:3.10-slim (~50 МБ вместо ~900 МБ у full)
#
# Размер итогового образа: ~2.5 ГБ (PyTorch + EasyOCR модели)
# Время первого запуска: ~60 сек (загрузка моделей EasyOCR)

# ═══════════════════════════════════════════════════════════════════════════════
# ЭТАП 1: Сборка зависимостей
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.10-slim AS builder

# Метаданные образа
LABEL maintainer="Uzbek OCR Team"
LABEL description="Uzbek OCR Backend — EasyOCR + FastAPI (CPU)"

# Системные переменные для не-интерактивной установки пакетов
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ── Системные зависимости ─────────────────────────────────────────────────────
#
# Пакеты необходимы для:
#   libgl1-mesa-glx     — OpenCV (рендеринг через OpenGL)
#   libglib2.0-0        — GLib (зависимость OpenCV)
#   libgomp1            — OpenMP (параллельные вычисления в PyTorch)
#   libsm6 libxext6     — X11 расширения для OpenCV
#   libxrender1         — Рендеринг шрифтов
#   libopencv-dev       — Заголовки OpenCV для сборки
#   wget curl           — Загрузка файлов (для скачивания моделей)
#   git                 — EasyOCR скачивает модели через git иногда

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        wget \
        curl \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Установка Python зависимостей ─────────────────────────────────────────────
#
# Используем виртуальное окружение для изоляции зависимостей.
# Это позволяет легко скопировать только venv на следующий этап.

WORKDIR /install

# Создаём виртуальное окружение
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копируем только requirements.txt для кэширования Docker слоя.
# Если requirements.txt не изменился — Docker использует кэш
# и не переустанавливает зависимости при каждой сборке.
COPY requirements.txt .

# ── Установка PyTorch (CPU-версия) ────────────────────────────────────────────
#
# CPU-версия значительно меньше GPU (~700 МБ вместо ~3 ГБ).
# Скачиваем из официального репозитория PyTorch.
RUN pip install --upgrade pip setuptools wheel && \
    pip install torch==2.5.1 torchvision==0.20.1 \
        --index-url https://download.pytorch.org/whl/cpu

# ── Установка остальных зависимостей из requirements.txt ─────────────────────
# torch/torchvision уже установлены выше — исключаем их чтобы pip не пытался
# переустановить из стандартного индекса (там нет CPU-wheel для aarch64).
COPY requirements.txt .
RUN grep -v '^torch' requirements.txt | pip install -r /dev/stdin


# ═══════════════════════════════════════════════════════════════════════════════
# ЭТАП 2: Финальный образ (runtime)
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.10-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Путь к виртуальному окружению
    PATH="/opt/venv/bin:$PATH" \
    # Директория для кэша EasyOCR моделей
    EASYOCR_MODULE_PATH="/app/model"

# ── Минимальный набор системных библиотек для runtime ────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Копируем виртуальное окружение из builder ─────────────────────────────────
COPY --from=builder /opt/venv /opt/venv

# ── Настройка рабочей директории ─────────────────────────────────────────────
WORKDIR /app

# ── Создаём непривилегированного пользователя (best practice безопасности) ───
RUN groupadd --gid 1001 ocr && \
    useradd --uid 1001 --gid ocr --shell /bin/bash --create-home ocr

# ── Копируем исходный код ─────────────────────────────────────────────────────
#
# Порядок важен: сначала копируем модели (редко меняются),
# потом код (меняется часто). Это оптимизирует кэширование Docker слоёв.

# Директория с моделями EasyOCR и словарём
COPY --chown=ocr:ocr model/ ./model/

# Исходный код бэкенда
COPY --chown=ocr:ocr main.py \
                     homoglyph_normalizer.py \
                     spelling_corrector.py \
                     layout_reconstructor.py \
                     celery_app.py \
                     ocr_tasks.py \
                     generate_latin_dict.py \
                     image_preprocessor.py \
                     ./

# ── Переключаемся на непривилегированного пользователя ───────────────────────
USER ocr

# ── Проверка работоспособности (Health Check) ────────────────────────────────
#
# Docker периодически проверяет, что контейнер живой.
# Если /health не отвечает 3 раза подряд — контейнер помечается unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Открываем порт ────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Команда запуска ───────────────────────────────────────────────────────────
#
# Параметры uvicorn:
#   --host 0.0.0.0      — слушаем все интерфейсы (нужно для Docker)
#   --port 8000         — порт приложения
#   --workers 1         — один воркер (EasyOCR не thread-safe)
#   --log-level info    — уровень логирования
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
