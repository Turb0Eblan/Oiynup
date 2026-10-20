"""
Oiynup — главный оркестратор устройства.

Запуск: python main.py
Для режима отладки: python main.py --debug

Архитектура:
  - Все модули запускаются в своих потоках
  - События от микрофона и камеры передаются в AI бэкенд
  - Ответы AI исполняются: TTS → динамик, анимации → матрица, SMS → родители
  - AI подключается через BaseAIBackend (ai_interface.py)

Для интеграции своего AI:
  1. Создайте класс MyAI(BaseAIBackend) в своём файле
  2. Реализуйте метод process_event()
  3. В этом файле замените MockAIBackend на MyAI
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

# Добавляем src в путь (если запуск из корня проекта)
sys.path.insert(0, os.path.dirname(__file__))

from config import config, SystemConfig
from ai_interface import (
    BaseAIBackend,
    DeviceEvent,
    EventType,
    MockAIBackend,
    ResponseType,
)
from camera import CameraModule
from audio_input import AudioInputModule
from audio_output import AudioOutputModule
from gsm import GsmModule
from led_matrix import LedMatrix

logger = logging.getLogger(__name__)


class OiynupDevice:
    """
    Главный класс устройства.

    Связывает все модули и AI бэкенд.
    """

    def __init__(self, cfg: SystemConfig, ai_backend: Optional[BaseAIBackend] = None) -> None:
        self.cfg = cfg
        self.ai: BaseAIBackend = ai_backend or MockAIBackend()

        # Инициализация модулей
        self.camera = CameraModule(cfg.camera)
        self.mic = AudioInputModule(cfg.audio_input)
        self.speaker = AudioOutputModule(cfg.audio_output)
        self.gsm = GsmModule(cfg.gsm)
        self.led = LedMatrix(cfg.led)

        self._running = False
        self._shutdown_event = threading.Event()

    # ------------------------------------------------------------------
    # Жизненный цикл
    # ------------------------------------------------------------------

    def start(self) -> None:
        logger.info("=== Oiynup запускается ===")
        self._running = True

        # Запускаем модули
        self.led.start()
        self.speaker.start()
        self.gsm.start()
        self.camera.start()
        self.mic.start()

        # Подключаем обработчики событий
        self.mic.add_phrase_callback(self._on_phrase)
        self.mic.add_chunk_callback(self._on_chunk)   # непрерывный стрим для мониторинга
        self.camera.add_frame_callback(self._on_frame)

        # Запускаем AI бэкенд
        self.ai.on_start()

        # Визуальный старт — радуга на 3 секунды
        self.led.animation("rainbow", duration_sec=3)

        # Отправляем событие старта
        self._dispatch_event(DeviceEvent(type=EventType.SYSTEM_START))

        # GSM уведомление родителю
        threading.Thread(
            target=lambda: self.gsm.send_parent_alert("system_start"),
            daemon=True,
        ).start()

        logger.info("=== Oiynup готов к работе ===")

    def stop(self) -> None:
        logger.info("=== Oiynup останавливается ===")
        self._running = False

        self._dispatch_event(DeviceEvent(type=EventType.SYSTEM_STOP))
        self.gsm.send_parent_alert("system_stop")

        self.ai.on_stop()
        self.camera.stop()
        self.mic.stop()
        self.speaker.stop()
        self.gsm.stop()
        self.led.stop()

        self._shutdown_event.set()
        logger.info("=== Oiynup остановлен ===")

    def run_forever(self) -> None:
        """Блокирующий запуск до сигнала остановки."""
        self.start()
        try:
            self._shutdown_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # ------------------------------------------------------------------
    # Обработчики событий от железа
    # ------------------------------------------------------------------

    def _on_chunk(self, chunk_bytes: bytes) -> None:
        """Каждый сырой чанк — для real-time аудио мониторинга."""
        if not self._running:
            return
        if hasattr(self.ai, 'send_raw_chunk'):
            self.ai.send_raw_chunk(chunk_bytes)

    def _on_phrase(self, audio_bytes: bytes) -> None:
        """Микрофон: закончена фраза — передаём в AI."""
        if not self._running:
            return
        logger.debug("Фраза получена: %d байт", len(audio_bytes))
        self.led.animation("listening", duration_sec=0)
        event = DeviceEvent(
            type=EventType.AUDIO_CHUNK,
            data=audio_bytes,
            metadata={
                "sample_rate": self.cfg.audio_input.sample_rate,
                "channels": self.cfg.audio_input.channels,
                "format": "pcm_s16le",
            },
        )
        self._dispatch_event(event)

    def _on_frame(self, frame) -> None:
        """Камера: новый кадр — передаём в AI."""
        if not self._running:
            return
        event = DeviceEvent(
            type=EventType.VIDEO_FRAME,
            data=frame,
            metadata={
                "resolution": self.cfg.camera.resolution,
                "format": "bgr888",
            },
        )
        self._dispatch_event(event)

    # ------------------------------------------------------------------
    # Диспетчеризация
    # ------------------------------------------------------------------

    def _dispatch_event(self, event: DeviceEvent) -> None:
        """Отправить событие в AI и выполнить ответы."""
        try:
            responses = self.ai.process_event(event)
        except Exception as exc:
            logger.error("AI бэкенд вернул ошибку: %s", exc)
            return

        for response in responses:
            self._execute_response(response)

    def _execute_response(self, response) -> None:
        """Выполнить один ответ AI на устройстве."""
        try:
            if response.type == ResponseType.SPEAK:
                if response.audio_bytes:
                    self.speaker.play_bytes(response.audio_bytes, priority=response.priority)
                elif response.text:
                    self.speaker.speak(
                        response.text,
                        language=self.cfg.language,
                        priority=response.priority,
                    )

            elif response.type == ResponseType.DISPLAY:
                if response.display:
                    d = response.display
                    self.led.animation(
                        name=d.animation,
                        color=d.color,
                        duration_sec=d.duration_sec,
                    )

            elif response.type == ResponseType.SMS_PARENT:
                if response.text:
                    threading.Thread(
                        target=lambda t=response.text, p=response.phone: self.gsm.send_sms(t, phone=p),
                        daemon=True,
                    ).start()

            elif response.type == ResponseType.LESSON_UPDATE:
                logger.info("Обновление урока: %s", response.lesson_data)
                # Коллеги: здесь можно сохранить в БД, отобразить на экране и т.д.

            elif response.type == ResponseType.IDLE:
                pass  # ничего не делаем

        except Exception as exc:
            logger.error("Ошибка выполнения ответа AI (%s): %s", response.type, exc)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.log_file, encoding="utf-8"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Oiynup — детское AI устройство")
    parser.add_argument("--debug", action="store_true", help="Подробное логирование")
    parser.add_argument(
        "--ai",
        default="mock",
        help="AI бэкенд: 'mock' (по умолчанию) или путь к модулю",
    )
    parser.add_argument(
        "--ws",
        default=None,
        metavar="URL",
        help="Один WebSocket: ws://192.168.1.100:8765",
    )
    parser.add_argument(
        "--dual-ws",
        default=None,
        metavar="HOST",
        help="Два WebSocket (аудио + видео): 192.168.1.100  "
             "Порты: аудио=8765, видео=8766 (или HOST:audio_port:video_port)",
    )
    args = parser.parse_args()

    setup_logging(args.debug)

    # Создаём директорию для данных
    os.makedirs(config.data_dir, exist_ok=True)

    # Выбираем AI бэкенд
    if args.dual_ws:
        from streaming import DualStreamBackend
        # Формат: HOST  или  HOST:audio_port:video_port
        parts = args.dual_ws.split(":")
        host = parts[0]
        audio_port = int(parts[1]) if len(parts) > 1 else 8765
        video_port = int(parts[2]) if len(parts) > 2 else 8766
        logger.info("Режим: Dual WebSocket → %s (audio:%d, video:%d)",
                    host, audio_port, video_port)
        ai_backend = DualStreamBackend(host, audio_port, video_port)
    elif args.ws:
        from streaming import WebSocketAIBackend
        logger.info("Режим: WebSocket AI сервер → %s", args.ws)
        ai_backend = WebSocketAIBackend(args.ws)
    else:
        logger.info("Режим: MockAI (заглушка)")
        ai_backend = MockAIBackend()

    device = OiynupDevice(cfg=config, ai_backend=ai_backend)

    # Обработчики сигналов ОС
    def handle_signal(sig, frame):
        logger.info("Получен сигнал %s", sig)
        device.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    device.run_forever()


if __name__ == "__main__":
    main()
