"""
Oiynup — модуль RGB матрицы (WS2812B / NeoPixel).

Подключение: GPIO10 (SPI MOSI, Pin 19)
Библиотека: rpi_ws281x

Предоставляет готовые анимации для детского устройства:
  - idle: пульсирующий синий
  - happy: зелёные огни
  - thinking: вращающийся жёлтый
  - correct: вспышка зелёного
  - wrong: вспышка красного
  - rainbow: радуга
  - listening: голубое мерцание
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Optional

from config import LedMatrixConfig

logger = logging.getLogger(__name__)

try:
    from rpi_ws281x import PixelStrip, Color as WsColor
    HAS_WS281X = True
except ImportError:
    HAS_WS281X = False
    logger.warning("rpi_ws281x не найдена — LED матрица в режиме заглушки")


def _color(r: int, g: int, b: int) -> int:
    """Конвертация RGB в формат WS2812B GRB (библиотека сама переставит)."""
    if HAS_WS281X:
        return WsColor(r, g, b)
    return (r << 16) | (g << 8) | b


class LedMatrix:
    def __init__(self, cfg: LedMatrixConfig) -> None:
        self.cfg = cfg
        self._strip = None
        self._anim_thread: Optional[threading.Thread] = None
        self._stop_anim = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Управление жизненным циклом
    # ------------------------------------------------------------------

    def start(self) -> None:
        if HAS_WS281X:
            pwm_channel = 1 if self.cfg.pin == 13 else 0
            try:
                self._strip = PixelStrip(
                    num=self.cfg.num_pixels,
                    pin=self.cfg.pin,
                    channel=pwm_channel,
                    brightness=int(self.cfg.brightness * 255),
                    strip_type=None,
                )
                self._strip.begin()
                logger.info("LED матрица запущена: %d пикселей (GPIO%d, PWM channel %d)",
                            self.cfg.num_pixels, self.cfg.pin, pwm_channel)
            except Exception as exc:
                # Нет доступа к /dev/mem (не root) — работаем в заглушке
                logger.warning("LED матрица недоступна (%s) — режим заглушки", exc)
                self._strip = None
        else:
            logger.info("[stub] LED матрица: %d пикселей (заглушка)", self.cfg.num_pixels)

        self.animation("idle")

    def stop(self) -> None:
        self._stop_animation()
        self.fill(0, 0, 0)
        self._show()
        logger.info("LED матрица выключена")

    # ------------------------------------------------------------------
    # Базовые операции
    # ------------------------------------------------------------------

    def fill(self, r: int, g: int, b: int) -> None:
        """Заполнить всю матрицу одним цветом."""
        if self._strip is None:
            logger.debug("[stub] LED fill RGB(%d,%d,%d)", r, g, b)
            return
        for i in range(self.cfg.num_pixels):
            self._strip.setPixelColor(i, _color(r, g, b))

    def set_pixel(self, index: int, r: int, g: int, b: int) -> None:
        if self._strip:
            self._strip.setPixelColor(index, _color(r, g, b))

    def _show(self) -> None:
        if self._strip:
            self._strip.show()

    # ------------------------------------------------------------------
    # Анимации
    # ------------------------------------------------------------------

    def animation(self, name: str, color: tuple[int, int, int] = (0, 100, 255), duration_sec: float = 0) -> None:
        """
        Запустить именованную анимацию.

        Args:
            name: "idle", "happy", "thinking", "correct", "wrong", "rainbow", "listening"
            color: RGB цвет для анимаций, поддерживающих кастомный цвет
            duration_sec: 0 = бесконечно пока не вызовется другая анимация
        """
        self._stop_animation()
        self._stop_anim.clear()

        anim_map = {
            "idle": self._anim_idle,
            "happy": self._anim_happy,
            "thinking": self._anim_thinking,
            "correct": self._anim_correct,
            "wrong": self._anim_wrong,
            "rainbow": self._anim_rainbow,
            "listening": self._anim_listening,
        }

        fn = anim_map.get(name, self._anim_idle)

        def run():
            start = time.time()
            while not self._stop_anim.is_set():
                fn(color)
                if duration_sec > 0 and time.time() - start >= duration_sec:
                    break
            self.fill(0, 0, 0)
            self._show()

        self._anim_thread = threading.Thread(target=run, daemon=True)
        self._anim_thread.start()

    def _stop_animation(self) -> None:
        self._stop_anim.set()
        if self._anim_thread and self._anim_thread.is_alive():
            self._anim_thread.join(timeout=2)

    # ------------------------------------------------------------------
    # Конкретные анимации
    # ------------------------------------------------------------------

    def _anim_idle(self, color: tuple) -> None:
        """Медленное пульсирование синего."""
        for step in range(100):
            if self._stop_anim.is_set():
                return
            t = math.sin(step * math.pi / 50)
            brightness = int((t * 0.4 + 0.6) * color[2])
            self.fill(0, 0, brightness)
            self._show()
            time.sleep(0.03)

    def _anim_happy(self, color: tuple) -> None:
        """Весёлые зелёные огни."""
        import random
        for _ in range(30):
            if self._stop_anim.is_set():
                return
            for i in range(self.cfg.num_pixels):
                r = random.randint(0, 80)
                self.set_pixel(i, r, 200, r // 2)
            self._show()
            time.sleep(0.1)

    def _anim_thinking(self, color: tuple) -> None:
        """Вращающаяся жёлтая точка — робот думает."""
        for i in range(self.cfg.num_pixels):
            if self._stop_anim.is_set():
                return
            self.fill(0, 0, 0)
            self.set_pixel(i % self.cfg.num_pixels, 255, 200, 0)
            self.set_pixel((i + 1) % self.cfg.num_pixels, 100, 80, 0)
            self._show()
            time.sleep(0.05)

    def _anim_correct(self, color: tuple) -> None:
        """Вспышка зелёного — правильный ответ!"""
        for _ in range(3):
            if self._stop_anim.is_set():
                return
            self.fill(0, 255, 50)
            self._show()
            time.sleep(0.15)
            self.fill(0, 0, 0)
            self._show()
            time.sleep(0.1)

    def _anim_wrong(self, color: tuple) -> None:
        """Вспышка красного — попробуй ещё раз."""
        for _ in range(2):
            if self._stop_anim.is_set():
                return
            self.fill(255, 30, 0)
            self._show()
            time.sleep(0.2)
            self.fill(0, 0, 0)
            self._show()
            time.sleep(0.15)

    def _anim_rainbow(self, color: tuple) -> None:
        """Радуга по всей матрице."""
        n = self.cfg.num_pixels
        for offset in range(256):
            if self._stop_anim.is_set():
                return
            for i in range(n):
                hue = (i * 256 // n + offset) & 255
                r, g, b = self._wheel(hue)
                self.set_pixel(i, r, g, b)
            self._show()
            time.sleep(0.02)

    def _anim_listening(self, color: tuple) -> None:
        """Голубое мерцание — устройство слушает."""
        for step in range(60):
            if self._stop_anim.is_set():
                return
            v = int(abs(math.sin(step * math.pi / 15)) * 180) + 30
            self.fill(0, v // 3, v)
            self._show()
            time.sleep(0.04)

    @staticmethod
    def _wheel(pos: int) -> tuple[int, int, int]:
        """Цветовое колесо 0-255 → RGB."""
        pos = 255 - pos
        if pos < 85:
            return (255 - pos * 3, 0, pos * 3)
        if pos < 170:
            pos -= 85
            return (0, pos * 3, 255 - pos * 3)
        pos -= 170
        return (pos * 3, 255 - pos * 3, 0)
