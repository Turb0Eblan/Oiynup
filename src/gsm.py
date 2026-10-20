"""
Oiynup — модуль GSM (SIM900).

Возможности:
  - Отправка SMS родителям
  - Проверка уровня сигнала
  - Автоповтор при ошибке

UART: GPIO14 (TX) / GPIO15 (RX) → /dev/ttyS0
Питание SIM900: внешний 5V/2A (не от RPi!)
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Optional

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

from config import GsmConfig

logger = logging.getLogger(__name__)

# Кодировки для кирилицы в SMS
GSM_CHARSET = "UCS2"      # поддерживает казахский и русский


class GsmModule:
    def __init__(self, cfg: GsmConfig) -> None:
        self.cfg = cfg
        self._serial: Optional[object] = None
        self._ready = False

    # ------------------------------------------------------------------
    # Управление жизненным циклом
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not HAS_SERIAL:
            logger.warning("pyserial не найдена — GSM в режиме заглушки")
            return
        if not HAS_GPIO:
            logger.warning("RPi.GPIO не найдена — без сброса модуля")

        self._setup_gpio()
        self._open_serial()
        self._initialize_modem()

    def stop(self) -> None:
        if self._serial and hasattr(self._serial, 'close'):
            self._serial.close()
        logger.info("GSM модуль остановлен")

    # ------------------------------------------------------------------
    # Публичное API
    # ------------------------------------------------------------------

    def send_sms(self, text: str, phone: Optional[str] = None, retries: int = 3) -> bool:
        """
        Отправить SMS.

        Args:
            text: Текст сообщения (поддерживает кириллицу)
            phone: Номер получателя. None → берёт из конфига (parent_phone)
            retries: Количество попыток при ошибке

        Returns:
            True если SMS отправлена успешно
        """
        number = phone or self.cfg.parent_phone
        if not number:
            logger.error("Номер телефона не указан")
            return False

        for attempt in range(1, retries + 1):
            try:
                ok = self._send_sms_once(number, text)
                if ok:
                    logger.info("SMS отправлена на %s", number)
                    return True
                logger.warning("Попытка %d/%d: SMS не отправлена", attempt, retries)
            except Exception as exc:
                logger.error("Попытка %d/%d: %s", attempt, retries, exc)
            time.sleep(2)

        logger.error("SMS не удалось отправить после %d попыток", retries)
        return False

    def send_parent_alert(self, event: str) -> bool:
        """Быстрый метод — отправить стандартное уведомление родителю."""
        messages = {
            "low_battery": "Ойнап: низкий заряд батареи",
            "child_crying": "Ойнап: ребёнок плачет",
            "system_start": "Ойнап: устройство включено",
            "system_stop": "Ойнап: устройство выключено",
        }
        text = messages.get(event, f"Ойнап: {event}")
        return self.send_sms(text)

    def get_signal_strength(self) -> Optional[int]:
        """Уровень сигнала 0-31 (99 = нет сигнала)."""
        response = self._at("AT+CSQ")
        if response and "+CSQ:" in response:
            try:
                return int(response.split(":")[1].strip().split(",")[0])
            except (ValueError, IndexError):
                pass
        return None

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _setup_gpio(self) -> None:
        if not HAS_GPIO:
            return
        GPIO.setmode(GPIO.BCM)
        # Only touch RST pin — never setup GPIO14/15 (UART TX/RX), it would break the UART
        GPIO.setup(self.cfg.reset_pin, GPIO.OUT)
        GPIO.output(self.cfg.reset_pin, GPIO.HIGH)

    def _open_serial(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self.cfg.port,
                baudrate=self.cfg.baudrate,
                timeout=self.cfg.timeout_sec,
            )
            logger.info("UART открыт: %s @ %d", self.cfg.port, self.cfg.baudrate)
        except Exception as exc:
            logger.error("Не удалось открыть UART: %s", exc)

    def _initialize_modem(self) -> None:
        if self._serial is None:
            return
        time.sleep(2)  # ждём загрузки SIM900

        tests = [
            ("AT", "OK"),
            ("AT+CMGF=1", "OK"),             # текстовый режим SMS
            (f'AT+CSCS="{GSM_CHARSET}"', "OK"),  # кодировка
        ]
        for cmd, expected in tests:
            resp = self._at(cmd)
            if resp and expected in resp:
                logger.debug("AT команда OK: %s", cmd)
            else:
                logger.warning("AT команда не ответила: %s → %s", cmd, resp)
                return

        self._ready = True
        logger.info("SIM900 инициализирован и готов")

    def _at(self, command: str, wait_sec: float = 1.0) -> Optional[str]:
        if self._serial is None:
            logger.debug("[stub] AT: %s", command)
            return "OK"   # заглушка

        try:
            self._serial.write((command + "\r\n").encode())
            time.sleep(wait_sec)
            raw = self._serial.read_all()
            return raw.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            logger.error("AT ошибка (%s): %s", command, exc)
            return None

    def _send_sms_once(self, number: str, text: str) -> bool:
        if self._serial is None:
            logger.info("[stub] SMS → %s: %s", number, text)
            return True

        # Убеждаемся что GSM charset установлен (поддерживает латиницу и транслитерацию)
        self._serial.write(b'AT+CSCS="GSM"\r\n')
        time.sleep(1)
        self._serial.read_all()

        # Отправляем команду и ждём > промпт от SIM900
        self._serial.write(f'AT+CMGS="{number}"\r'.encode())
        time.sleep(2)  # SIM900 может отвечать с задержкой до 2 сек
        prompt = self._serial.read_all().decode("utf-8", errors="replace")
        if ">" not in prompt:
            logger.warning("SIM900 не дал > промпт: %s", repr(prompt))
            return False

        # Отправляем текст + Ctrl+Z (0x1A)
        self._serial.write(f"{text}\x1a".encode("utf-8", errors="replace"))
        time.sleep(5)  # отправка может занимать до 5 сек

        response = self._serial.read_all().decode("utf-8", errors="replace")
        logger.debug("SMS response: %s", repr(response))
        return "+CMGS:" in response

    def hardware_reset(self) -> None:
        """Аппаратный сброс через GPIO (если SIM900 завис)."""
        if not HAS_GPIO:
            return
        logger.info("Аппаратный сброс SIM900")
        GPIO.output(self.cfg.reset_pin, GPIO.LOW)
        time.sleep(1)
        GPIO.output(self.cfg.reset_pin, GPIO.HIGH)
        time.sleep(3)
        self._initialize_modem()
