"""
Oiynup — модуль записи звука.
INMP441 (I2S) → pyaudio device=0 → Python.
ALSA plug (asound.conf) конвертирует форматы автоматически.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np

from config import AudioInputConfig

logger = logging.getLogger(__name__)


class AudioInputModule:
    def __init__(self, cfg: AudioInputConfig) -> None:
        self.cfg = cfg
        self._pa = None
        self._stream = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._phrase_callbacks: list[Callable[[bytes], None]] = []
        self._chunk_callbacks: list[Callable[[bytes], None]] = []

    def start(self) -> None:
        self._open_stream()
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("Аудио-вход запущен: %dHz device=%d",
                    self.cfg.sample_rate, self.cfg.device_index)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
        logger.info("Аудио-вход остановлен")

    def add_phrase_callback(self, cb: Callable[[bytes], None]) -> None:
        self._phrase_callbacks.append(cb)

    def add_chunk_callback(self, cb: Callable[[bytes], None]) -> None:
        self._chunk_callbacks.append(cb)

    def _open_stream(self) -> None:
        try:
            import pyaudio
            self._pa = pyaudio.PyAudio()
            # Не указываем device_index — pyaudio использует ALSA "default"
            # который идёт через plug в asound.conf → поддерживает 16kHz
            self._stream = self._pa.open(
                format=pyaudio.paInt32,
                channels=self.cfg.channels,
                rate=self.cfg.sample_rate,
                input=True,
                frames_per_buffer=self.cfg.chunk_size,
            )
            logger.info("PyAudio открыт: default device, %dHz", self.cfg.sample_rate)
        except ImportError:
            logger.warning("pyaudio не найдена — режим заглушки")
        except Exception as exc:
            logger.error("Не удалось открыть mic: %s", exc)

    def _extract_mono(self, raw: bytes) -> np.ndarray:
        """I2S int32 стерео → int16 моно."""
        s = np.frombuffer(raw, dtype=np.int32)
        mono = s[self.cfg.use_channel::self.cfg.channels].copy()
        return (mono >> 16).astype(np.int16)

    def _rms(self, s: np.ndarray) -> float:
        if not len(s):
            return 0.0
        return float(np.sqrt(np.mean(s.astype(np.float32) ** 2))) / 32768.0

    def _listen_loop(self) -> None:
        cfg = self.cfg
        silence_limit = int(cfg.silence_duration_sec * cfg.sample_rate / cfg.chunk_size)
        phrase_buf: list[bytes] = []
        in_phrase = False
        silence_cnt = 0

        while self._running:
            if self._stream is None:
                import time; time.sleep(0.1)
                continue
            try:
                raw = self._stream.read(cfg.chunk_size, exception_on_overflow=False)
            except Exception as exc:
                logger.warning("Ошибка чтения: %s", exc)
                continue

            samples = self._extract_mono(raw)
            chunk_bytes = samples.tobytes()

            for cb in self._chunk_callbacks:
                try: cb(chunk_bytes)
                except Exception as e: logger.error("chunk cb: %s", e)

            rms = self._rms(samples)
            speech = rms > cfg.silence_threshold

            if speech:
                if not in_phrase:
                    logger.debug("Речь (RMS=%.4f)", rms)
                in_phrase = True
                silence_cnt = 0
                phrase_buf.append(chunk_bytes)
            elif in_phrase:
                phrase_buf.append(chunk_bytes)
                silence_cnt += 1
                if silence_cnt >= silence_limit:
                    data = b"".join(phrase_buf)
                    for cb in self._phrase_callbacks:
                        try: cb(data)
                        except Exception as e: logger.error("phrase cb: %s", e)
                    phrase_buf.clear()
                    in_phrase = False
                    silence_cnt = 0
