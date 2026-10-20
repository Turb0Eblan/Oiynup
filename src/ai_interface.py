"""
Oiynup — интерфейс для AI-системы.

Коллеги: реализуйте класс AIBackend, наследуясь от BaseAIBackend.
Пример реализации — MockAIBackend внизу файла.

Интерфейс намеренно синхронный для простоты;
при необходимости оберните в asyncio.

Типы событий, которые устройство отправляет в AI:
  - audio_chunk: аудио от микрофона (PCM bytes)
  - video_frame: кадр с камеры (numpy array BGR)
  - button_press: нажатие кнопки (если добавите)
  - system_start / system_stop

Типы ответов AI:
  - speak: текст для TTS или готовый аудио-буфер
  - display: команда для RGB матрицы (анимация/цвет/текст)
  - sms_parent: текст SMS родителю
  - lesson_update: новый контент урока
  - idle: ничего не делать
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Типы данных — входящие события
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    AUDIO_CHUNK = "audio_chunk"
    VIDEO_FRAME = "video_frame"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    BUTTON_PRESS = "button_press"


@dataclass
class DeviceEvent:
    """Событие от устройства к AI."""
    type: EventType
    data: Any = None                       # зависит от типа
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Типы данных — ответы AI
# ---------------------------------------------------------------------------

class ResponseType(str, Enum):
    SPEAK = "speak"
    DISPLAY = "display"
    SMS_PARENT = "sms_parent"
    LESSON_UPDATE = "lesson_update"
    IDLE = "idle"


@dataclass
class DisplayCommand:
    """Команда для RGB матрицы."""
    animation: str = "idle"               # "idle", "happy", "thinking", "correct", "wrong"
    color: tuple[int, int, int] = (0, 100, 255)  # RGB
    duration_sec: float = 2.0
    text: Optional[str] = None           # если матрица поддерживает текст


@dataclass
class AIResponse:
    """Ответ AI-системы на событие."""
    type: ResponseType
    text: Optional[str] = None           # для SPEAK и SMS_PARENT
    audio_bytes: Optional[bytes] = None  # готовый PCM/WAV, если AI сам синтезировал
    display: Optional[DisplayCommand] = None
    lesson_data: Optional[dict] = None   # произвольные данные урока
    priority: int = 5                    # 1 (высокий) … 10 (низкий)
    phone: Optional[str] = None          # для SMS_PARENT: номер получателя


# ---------------------------------------------------------------------------
# Базовый класс — реализуйте его
# ---------------------------------------------------------------------------

class BaseAIBackend(ABC):
    """
    Абстрактный AI-бэкенд.

    Минимальная реализация требует только process_event().
    Остальные методы имеют дефолтные заглушки.
    """

    def on_start(self) -> None:
        """Вызывается при запуске системы. Инициализируйте модели здесь."""
        pass

    def on_stop(self) -> None:
        """Вызывается при остановке. Освободите ресурсы."""
        pass

    @abstractmethod
    def process_event(self, event: DeviceEvent) -> list[AIResponse]:
        """
        Главная точка входа.

        Получает событие от устройства, возвращает список ответов.
        Можно вернуть пустой список если реакция не нужна.

        Args:
            event: DeviceEvent с type и data

        Returns:
            Список AIResponse, которые система выполнит по очереди
        """

    def get_greeting(self, language: str = "kk") -> str:
        """Приветствие при включении. Переопределите под свою AI."""
        greetings = {
            "kk": "Сәлем! Мен сенің досың Ойнап!",
            "ru": "Привет! Я твой друг Ойнап!",
        }
        return greetings.get(language, greetings["ru"])

    def get_idle_display(self) -> DisplayCommand:
        """Что показывать на матрице когда ничего не происходит."""
        return DisplayCommand(animation="idle", color=(0, 50, 255))


# ---------------------------------------------------------------------------
# Пример-заглушка для тестирования железа без AI
# ---------------------------------------------------------------------------

class MockAIBackend(BaseAIBackend):
    """
    Минимальная заглушка для отладки железа.
    Отвечает эхом и случайными анимациями.
    """

    def on_start(self) -> None:
        logger.info("[MockAI] Запущен в режиме заглушки")

    def process_event(self, event: DeviceEvent) -> list[AIResponse]:
        if event.type == EventType.SYSTEM_START:
            # Только анимация — без звука (чтобы не мешать при тестировании)
            return [
                AIResponse(
                    type=ResponseType.DISPLAY,
                    display=DisplayCommand(animation="happy", color=(0, 255, 100)),
                ),
            ]

        if event.type == EventType.AUDIO_CHUNK:
            # Имитируем распознавание: просто подтверждаем получение
            logger.debug("[MockAI] Получен аудио-чанк, %d байт", len(event.data or b""))
            return []

        if event.type == EventType.VIDEO_FRAME:
            # Имитируем анализ кадра
            logger.debug("[MockAI] Получен кадр для анализа")
            return []

        return [AIResponse(type=ResponseType.IDLE)]
