"""
Oiynup — модуль вывода звука.
MAX98357 I2S → aplay -D plughw:0,0 (конвертация форматов автоматически).
TTS через espeak-ng.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import Optional

from config import AudioOutputConfig

logger = logging.getLogger(__name__)

ALSA_PLAY = "plughw:0,0"


@dataclass
class AudioTask:
    audio_bytes: Optional[bytes] = None
    text: Optional[str] = None
    language: str = "ru"
    priority: int = 5

    def __lt__(self, other: "AudioTask") -> bool:
        return self.priority < other.priority


class AudioOutputModule:
    def __init__(self, cfg: AudioOutputConfig) -> None:
        self.cfg = cfg
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._counter = 0
        self._lock = threading.Lock()
        self._current_proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Аудио-выход запущен (%s)", ALSA_PLAY)

    def stop(self) -> None:
        self._running = False
        self._kill()
        self._queue.put((0, 0, None))
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Аудио-выход остановлен")

    def speak(self, text: str, language: str = "ru", priority: int = 5) -> None:
        self._enqueue(AudioTask(text=text, language=language, priority=priority))

    def play_bytes(self, audio: bytes, priority: int = 5) -> None:
        self._enqueue(AudioTask(audio_bytes=audio, priority=priority))

    def play_file(self, path: str, priority: int = 5) -> None:
        try:
            with open(path, "rb") as f:
                self.play_bytes(f.read(), priority=priority)
        except OSError as exc:
            logger.error("play_file: %s", exc)

    def clear_queue(self) -> None:
        self._kill()
        while not self._queue.empty():
            try: self._queue.get_nowait()
            except queue.Empty: break

    def _enqueue(self, task: AudioTask) -> None:
        with self._lock:
            self._counter += 1
            self._queue.put((task.priority, self._counter, task))

    def _loop(self) -> None:
        while self._running:
            try:
                _, _, task = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            if task is None:
                break
            try:
                if task.audio_bytes:
                    self._play_bytes(task.audio_bytes)
                elif task.text:
                    self._tts(task.text, task.language)
            except Exception as exc:
                logger.error("Ошибка воспроизведения: %s", exc)

    def _play_bytes(self, data: bytes) -> None:
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(data)
                tmp = f.name
            proc = subprocess.Popen(
                ["aplay", "-D", ALSA_PLAY, "-q", tmp],
                stderr=subprocess.DEVNULL,
            )
            self._current_proc = proc
            proc.wait()
            self._current_proc = None
        except Exception as exc:
            logger.error("_play_bytes: %s", exc)
        finally:
            if tmp:
                try: os.unlink(tmp)
                except OSError: pass

    def _tts(self, text: str, language: str) -> None:
        lang = {"ru": "ru", "kk": "kk", "en": "en"}.get(language, "ru")
        try:
            espeak = subprocess.Popen(
                ["espeak-ng", "-v", lang, "--stdout", text],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            aplay = subprocess.Popen(
                ["aplay", "-D", ALSA_PLAY, "-q"],
                stdin=espeak.stdout, stderr=subprocess.DEVNULL,
            )
            espeak.stdout.close()
            self._current_proc = aplay
            aplay.wait()
            self._current_proc = None
        except FileNotFoundError:
            logger.warning("espeak-ng не найден: sudo apt install espeak-ng")
        except Exception as exc:
            logger.error("TTS: %s", exc)

    def _kill(self) -> None:
        p = self._current_proc
        if p and p.poll() is None:
            try: p.terminate(); p.wait(timeout=2)
            except Exception:
                try: p.kill()
                except Exception: pass
