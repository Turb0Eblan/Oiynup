"""
Oiynup — модуль камеры.

Использует picamera2 (для RPi OS Bullseye+).
Предоставляет: поток кадров для AI, фото по запросу.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

from config import CameraConfig

logger = logging.getLogger(__name__)


class CameraModule:
    def __init__(self, cfg: CameraConfig) -> None:
        self.cfg = cfg
        self._camera = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_callbacks: list[Callable[[np.ndarray], None]] = []

    # ------------------------------------------------------------------
    # Управление жизненным циклом
    # ------------------------------------------------------------------

    def start(self) -> None:
        try:
            from picamera2 import Picamera2
            # Проверяем наличие камеры до инициализации
            cameras = Picamera2.global_camera_info()
            if not cameras:
                logger.warning("Камера не найдена — работает в режиме заглушки")
                logger.warning("Проверь: лента CSI подключена? raspi-config → Camera → Enable?")
            else:
                self._camera = Picamera2()
                cam_config = self._camera.create_video_configuration(
                    main={"size": self.cfg.resolution, "format": "RGB888"},
                )
                self._camera.configure(cam_config)
                self._camera.start()
                logger.info("Камера запущена: %s (модель: %s)",
                            self.cfg.resolution, cameras[0].get('Model', 'unknown'))
        except ImportError:
            logger.warning("picamera2 не найдена — камера работает в режиме заглушки")
        except Exception as exc:
            logger.warning("Камера недоступна (%s) — работает в режиме заглушки", exc)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._camera:
            self._camera.stop()
            self._camera.close()
        logger.info("Камера остановлена")

    # ------------------------------------------------------------------
    # Подписка на кадры
    # ------------------------------------------------------------------

    def add_frame_callback(self, cb: Callable[[np.ndarray], None]) -> None:
        """AI-бэкенд регистрирует свой обработчик кадров здесь."""
        self._frame_callbacks.append(cb)

    def remove_frame_callback(self, cb: Callable[[np.ndarray], None]) -> None:
        self._frame_callbacks.discard(cb) if hasattr(self._frame_callbacks, 'discard') else None
        if cb in self._frame_callbacks:
            self._frame_callbacks.remove(cb)

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def capture_frame(self) -> Optional[np.ndarray]:
        """Вернуть один текущий кадр (BGR numpy array)."""
        if self._camera is None:
            return self._stub_frame()
        try:
            return self._camera.capture_array("main")
        except Exception as exc:
            logger.error("Ошибка захвата кадра: %s", exc)
            return None

    def capture_jpeg(self, quality: int = 85) -> Optional[bytes]:
        """Сохранить кадр как JPEG байты (для отправки/хранения)."""
        import cv2
        frame = self.capture_frame()
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        interval = self.cfg.capture_interval_sec
        while self._running:
            frame = self.capture_frame()
            if frame is not None and self._frame_callbacks:
                for cb in self._frame_callbacks:
                    try:
                        cb(frame)
                    except Exception as exc:
                        logger.error("Ошибка в frame callback: %s", exc)
            time.sleep(interval)

    @staticmethod
    def _stub_frame() -> np.ndarray:
        """Синяя рамка-заглушка когда камера недоступна."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :, 0] = 50   # синий канал
        return frame
