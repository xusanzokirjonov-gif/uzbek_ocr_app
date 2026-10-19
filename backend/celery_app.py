"""
celery_app.py
=============
Инициализация Celery-приложения для Uzbek OCR Backend.

Архитектура асинхронной обработки:
  ┌──────────────────────────────────────────────────────────────────┐
  │                       Клиент (Flutter)                           │
  │                            │                                     │
  │              POST /ocr/v2  │  ← загружает изображение           │
  │                            ▼                                     │
  │                     FastAPI Server                               │
  │                            │                                     │
  │          .delay()          │  ← ставит задачу в очередь         │
  │                            ▼                                     │
  │                    Redis (Broker)                                │
  │                            │                                     │
  │            consume         │  ← Celery Worker читает задачи     │
  │                            ▼                                     │
  │                    Celery Worker                                 │
  │                    (OCR Processing)                              │
  │                            │                                     │
  │          результат         │  ← сохраняет в Redis Backend       │
  │                            ▼                                     │
  │                    Redis (Result Backend)                        │
  │                            │                                     │
  │     GET /ocr/status/{id}   │  ← клиент опрашивает статус       │
  │                            ▼                                     │
  │                     FastAPI Server                               │
  └──────────────────────────────────────────────────────────────────┘

Конфигурация:
  - BROKER_URL: Redis как брокер сообщений (очередь задач)
  - RESULT_BACKEND: Redis как хранилище результатов задач
  - Сериализация: JSON (безопаснее pickle для продакшена)
  - TTL результатов: 1 час (достаточно для мобильного клиента)
"""

import os
from celery import Celery

# ─── macOS Apple Silicon: фикс SIGABRT при fork() ────────────────────────────
#
# PyTorch/EasyOCR инициализирует Metal Performance Shaders (MPS) при импорте.
# Celery использует prefork — дочерние процессы создаются через os.fork().
# На macOS fork() после инициализации Objective-C runtime вызывает SIGABRT:
#   objc: +[MPSGraphObject initialize] may have been in progress in another
#   thread when fork() was called. Crashing instead.
#
# Решение: OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES отключает этот guard.
# Запуск worker-а:
#   OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES celery -A celery_app worker ...
#
# В Docker (Linux) эта переменная не нужна — там нет Objective-C runtime.
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

# ─── Адрес Redis ──────────────────────────────────────────────────────────────
#
# В Docker Compose Redis доступен по имени сервиса "redis".
# Для локального запуска без Docker используйте REDIS_URL=redis://localhost:6379/0.
#
# Переменная окружения REDIS_URL задаётся в docker-compose.yml.

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ─── Создание Celery-приложения ───────────────────────────────────────────────
#
# Параметры:
#   "worker"          — имя приложения (отображается в логах воркера)
#   broker            — URL брокера сообщений (Redis)
#   backend           — URL хранилища результатов (Redis)
#
# Один Redis-инстанс используется и как брокер, и как backend.
# В продакшене можно разделить на разные базы (db=0 и db=1).

celery_app = Celery(
    "uzbek_ocr_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    # include: список модулей с задачами, которые worker импортирует при старте.
    # Без этого параметра [tasks] будет пустым и все входящие задачи
    # будут отброшены с ошибкой "Received unregistered task".
    include=["ocr_tasks"],
)

# ─── Конфигурация Celery ──────────────────────────────────────────────────────

celery_app.conf.update(
    # ── Сериализация ──────────────────────────────────────────────────────────
    #
    # JSON безопаснее pickle: не позволяет выполнить произвольный код Python
    # при десериализации задачи из брокера (важно для безопасности диплома).
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Временная зона ────────────────────────────────────────────────────────
    timezone="Asia/Tashkent",
    enable_utc=True,

    # ── TTL результатов ───────────────────────────────────────────────────────
    #
    # Результаты хранятся 1 час (3600 сек).
    # После истечения GET /ocr/status/{task_id} вернёт статус PENDING
    # (как если бы задача ещё не запускалась) — это стандартное поведение Celery.
    result_expires=3600,

    # ── Настройки очереди ─────────────────────────────────────────────────────
    #
    # task_acks_late=True: подтверждение задачи ПОСЛЕ её выполнения.
    # Если воркер упадёт во время OCR — задача вернётся в очередь (at-least-once).
    task_acks_late=True,

    # worker_prefetch_multiplier=1: воркер берёт одну задачу за раз.
    # Важно для тяжёлых OCR-задач, чтобы не перегружать память.
    worker_prefetch_multiplier=1,

    # ── Трекинг состояния ─────────────────────────────────────────────────────
    #
    # task_track_started=True: Celery публикует состояние STARTED
    # (наш кастомный пайплайн использует PROCESSING через update_state).
    task_track_started=True,

    # ── Таймауты задачи ───────────────────────────────────────────────────────
    #
    # Максимальное время выполнения OCR-задачи — 5 минут.
    # Если воркер завис — задача будет прервана.
    task_soft_time_limit=240,   # 4 мин: SoftTimeLimitExceeded (graceful)
    task_time_limit=300,        # 5 мин: жёсткое завершение (SIGKILL)
)
