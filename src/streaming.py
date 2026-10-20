"""
Oiynup — модуль WebSocket стриминга.

RPi (клиент) → подключается к AI серверу (сервер).
Отправляет: аудио (PCM), видео (JPEG), статус.
Получает:   команды (speak, display, sms, config).

Использование как AI бэкенд:
    from streaming import WebSocketAIBackend
    backend = WebSocketAIBackend(server_url="ws://ai-server:8765")
    device = OiynupDevice(cfg=config, ai_backend=backend)

Или как отдельный стрим поверх существующего бэкенда:
    streamer = OiynupStreamer(server_url="ws://ai-server:8765")
    streamer.start(device)
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import uuid
from typing import Optional, TYPE_CHECKING

import numpy as np

from ai_interface import (
    BaseAIBackend, DeviceEvent, EventType,
    AIResponse, ResponseType, DisplayCommand,
)
from config import config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Пытаемся импортировать websocket-client
try:
    import websocket
    HAS_WS = True
except ImportError:
    HAS_WS = False
    logger.warning("websocket-client не установлен: pip install websocket-client")


# ─────────────────────────────────────────────────────────────────────────────
#  Форматы сообщений протокола
# ─────────────────────────────────────────────────────────────────────────────

def _msg(msg_type: str, data=None, meta: dict = None) -> str:
    """Сформировать JSON сообщение протокола."""
    return json.dumps({
        "type":      msg_type,
        "id":        str(uuid.uuid4())[:8],
        "timestamp": time.time(),
        "data":      data,
        "meta":      meta or {},
    }, ensure_ascii=False)


def _audio_msg(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    return _msg(
        "audio",
        data=base64.b64encode(pcm_bytes).decode(),
        meta={"sample_rate": sample_rate, "channels": 1, "format": "pcm_s16le"},
    )


def _video_msg(jpeg_bytes: bytes, resolution: tuple) -> str:
    return _msg(
        "video",
        data=base64.b64encode(jpeg_bytes).decode(),
        meta={"format": "jpeg", "resolution": list(resolution)},
    )


def _status_msg(uptime: float, wifi_ip: str = "") -> str:
    return _msg(
        "status",
        meta={"uptime_sec": uptime, "wifi_ip": wifi_ip, "device": "oiynup"},
    )


def _event_msg(event_name: str, payload: dict = None) -> str:
    return _msg("event", meta={"event": event_name, **(payload or {})})


# ─────────────────────────────────────────────────────────────────────────────
#  WebSocket AI бэкенд — реализует BaseAIBackend через удалённый сервер
# ─────────────────────────────────────────────────────────────────────────────

class WebSocketAIBackend(BaseAIBackend):
    """
    AI бэкенд который стримит данные на удалённый WebSocket сервер
    и получает команды обратно.

    Использование:
        backend = WebSocketAIBackend("ws://192.168.1.100:8765")

    На сервере нужно реализовать WebSocket сервер который принимает
    сообщения протокола Oiynup и отвечает командами.
    """

    def __init__(self, server_url: str, reconnect_sec: float = 5.0,
                 on_reconnect=None):
        self.server_url = server_url
        self.reconnect_sec = reconnect_sec
        # Колбэк вызывается при повторном подключении: on_reconnect()
        self._on_reconnect_cb = on_reconnect
        self._ws: Optional[websocket.WebSocketApp] = None
        self._connected = False
        self._connection_count = 0          # 0 = ещё не подключались
        self._ws_thread: Optional[threading.Thread] = None
        self._response_queue: list[AIResponse] = []
        self._queue_lock = threading.Lock()
        self._start_time = time.time()

    # ── Жизненный цикл ────────────────────────────────────────────────────

    def on_start(self) -> None:
        logger.info("WebSocket AI бэкенд запускается: %s", self.server_url)
        self._ws_thread = threading.Thread(
            target=self._ws_loop, daemon=True,
        )
        self._ws_thread.start()

    def on_stop(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    # ── Обработка событий ─────────────────────────────────────────────────

    def process_event(self, event: DeviceEvent) -> list[AIResponse]:
        """Отправляем событие на сервер, возвращаем накопленные ответы."""
        if self._connected:
            self._send_event(event)

        with self._queue_lock:
            responses = list(self._response_queue)
            self._response_queue.clear()
        return responses

    def _send_event(self, event: DeviceEvent) -> None:
        try:
            if event.type == EventType.AUDIO_CHUNK and event.data:
                msg = _audio_msg(event.data, config.audio_input.sample_rate)
                self._ws.send(msg)

            elif event.type == EventType.VIDEO_FRAME and event.data is not None:
                # Конвертируем numpy → JPEG
                import cv2
                ok, buf = cv2.imencode(".jpg", event.data, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    msg = _video_msg(
                        buf.tobytes(),
                        event.metadata.get("resolution", (640, 480)),
                    )
                    self._ws.send(msg)

            elif event.type == EventType.SYSTEM_START:
                self._ws.send(_event_msg("system_start"))

            elif event.type == EventType.SYSTEM_STOP:
                self._ws.send(_event_msg("system_stop"))

        except Exception as exc:
            logger.warning("Ошибка отправки в WebSocket: %s", exc)
            self._connected = False

    # ── WebSocket подключение ─────────────────────────────────────────────

    def _ws_loop(self) -> None:
        """Цикл переподключения с экспоненциальным back-off."""
        delay = self.reconnect_sec
        while True:
            try:
                self._ws = websocket.WebSocketApp(
                    self.server_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
                delay = self.reconnect_sec  # сброс задержки после удачной сессии
            except Exception as exc:
                logger.error("WebSocket ошибка: %s", exc)
            logger.info("WebSocket переподключение через %.0f сек...", delay)
            time.sleep(delay)
            delay = min(delay * 2, 60.0)  # max 60 сек

    def _on_open(self, ws) -> None:
        self._connected = True
        self._connection_count += 1
        is_reconnect = self._connection_count > 1

        if is_reconnect:
            logger.info("WebSocket переподключён: %s", self.server_url)
            self._play_reconnect_sound()
            if self._on_reconnect_cb:
                try:
                    self._on_reconnect_cb()
                except Exception as exc:
                    logger.warning("on_reconnect callback ошибка: %s", exc)
        else:
            logger.info("WebSocket подключён: %s", self.server_url)

        uptime = time.time() - self._start_time
        ws.send(_status_msg(uptime))

    def _play_reconnect_sound(self) -> None:
        """Короткий бип через ALSA когда WebSocket восстановлен."""
        try:
            import struct, math
            sample_rate = 22050
            freq = 880          # Гц
            duration = 0.2      # сек
            num_samples = int(sample_rate * duration)
            # WAV PCM 16-bit заголовок + данные
            samples = bytes(
                struct.pack('<h', int(32767 * math.sin(2 * math.pi * freq * i / sample_rate)))
                for i in range(num_samples)
            )
            data_size = len(samples)
            wav_header = struct.pack('<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE', b'fmt ', 16,
                1, 1, sample_rate, sample_rate * 2, 2, 16, b'data', data_size)
            wav_bytes = wav_header + samples

            import tempfile, os, subprocess
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                f.write(wav_bytes)
                tmp = f.name
            subprocess.Popen(
                ['aplay', '-D', 'plughw:0,0', '-q', tmp],
                stderr=subprocess.DEVNULL,
            ).wait()
            os.unlink(tmp)
        except Exception as exc:
            logger.debug("Звук реконнекта не воспроизведён: %s", exc)

    def _on_close(self, ws, code, msg) -> None:
        self._connected = False
        logger.warning("WebSocket отключён (code=%s)", code)

    def _on_error(self, ws, error) -> None:
        self._connected = False
        logger.warning("WebSocket ошибка: %s", error)

    def _on_message(self, ws, raw: str) -> None:
        """Получаем команду от AI сервера, добавляем в очередь."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Неверный JSON от сервера: %s", raw[:80])
            return

        response = self._parse_command(msg)
        if response:
            with self._queue_lock:
                self._response_queue.append(response)

    def _parse_command(self, msg: dict) -> Optional[AIResponse]:
        """Разобрать входящую команду от AI сервера."""
        cmd = msg.get("type", "")

        if cmd == "speak":
            text = msg.get("text", "")
            audio_b64 = msg.get("audio")
            audio_bytes = base64.b64decode(audio_b64) if audio_b64 else None
            return AIResponse(
                type=ResponseType.SPEAK,
                text=text if not audio_bytes else None,
                audio_bytes=audio_bytes,
                priority=msg.get("priority", 5),
            )

        elif cmd == "display":
            d = msg.get("display", {})
            return AIResponse(
                type=ResponseType.DISPLAY,
                display=DisplayCommand(
                    animation=d.get("animation", "idle"),
                    color=tuple(d.get("color", [0, 100, 255])),
                    duration_sec=d.get("duration_sec", 2.0),
                ),
            )

        elif cmd == "sms":
            return AIResponse(
                type=ResponseType.SMS_PARENT,
                text=msg.get("text", ""),
                phone=msg.get("phone"),
            )

        elif cmd == "idle":
            return AIResponse(type=ResponseType.IDLE)

        elif cmd == "ping":
            # Отвечаем pong со статусом
            uptime = time.time() - self._start_time
            try:
                self._ws.send(_status_msg(uptime))
            except Exception:
                pass
            return None

        else:
            logger.debug("Неизвестная команда от сервера: %s", cmd)
            return None

    @property
    def is_connected(self) -> bool:
        return self._connected


# ─────────────────────────────────────────────────────────────────────────────
#  DualStreamBackend — два WebSocket: аудио (PCM) + видео (MJPEG)
#
#  RPi                    Server (Node.js)
#  ──────────────────────────────────────────────────────────────
#  binary PCM  ──ws:8765──▶ audioServer ──stdin──▶ ffmpeg ──▶ host
#  binary JPEG ──ws:8766──▶ videoServer ──pipe ──▶ ffmpeg
#
#  Запуск: python main.py --dual-ws 192.168.1.100
# ─────────────────────────────────────────────────────────────────────────────

def _play_beep() -> None:
    """Короткий 880 Гц бип через ALSA."""
    try:
        import struct, math, tempfile, os, subprocess
        sr, freq, dur = 22050, 880, 0.25
        n = int(sr * dur)
        samples = b"".join(
            struct.pack("<h", int(32767 * math.sin(2 * math.pi * freq * i / sr)))
            for i in range(n)
        )
        hdr = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + len(samples), b"WAVE", b"fmt ", 16,
            1, 1, sr, sr * 2, 2, 16, b"data", len(samples),
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(hdr + samples); tmp = f.name
        subprocess.Popen(["aplay", "-D", "plughw:0,0", "-q", tmp],
                         stderr=subprocess.DEVNULL).wait()
        os.unlink(tmp)
    except Exception as exc:
        logger.debug("Бип не воспроизведён: %s", exc)


class DualStreamBackend(BaseAIBackend):
    """
    Два WebSocket соединения для аудио и видео стримов:
      - Аудио (binary PCM s16le) + JSON-команды:  ws://host:audio_port
      - Видео (binary JPEG frames):               ws://host:video_port

    Оба соединения с авто-реконнектом и звуком при восстановлении.
    """

    def __init__(
        self,
        host: str,
        audio_port: int = 8765,
        video_port: int = 8766,
        reconnect_sec: float = 5.0,
    ):
        self._audio_url = f"ws://{host}:{audio_port}"
        self._video_url = f"ws://{host}:{video_port}"
        self._reconnect_sec = reconnect_sec

        self._audio_ws: Optional["websocket.WebSocketApp"] = None
        self._audio_connected = False
        self._audio_conn_count = 0

        self._video_ws: Optional["websocket.WebSocketApp"] = None
        self._video_connected = False
        self._video_conn_count = 0

        self._response_queue: list[AIResponse] = []
        self._queue_lock = threading.Lock()
        self._start_time = time.time()

    # ── Жизненный цикл ────────────────────────────────────────────────────

    def on_start(self) -> None:
        threading.Thread(target=self._audio_loop, daemon=True, name="ws-audio").start()
        threading.Thread(target=self._video_loop, daemon=True, name="ws-video").start()
        logger.info("DualStream: audio=%s  video=%s", self._audio_url, self._video_url)

    def on_stop(self) -> None:
        for ws in (self._audio_ws, self._video_ws):
            if ws:
                try: ws.close()
                except Exception: pass

    # ── Обработка событий ─────────────────────────────────────────────────

    def process_event(self, event: DeviceEvent) -> list[AIResponse]:
        if event.type == EventType.AUDIO_CHUNK and event.data:
            self._send_audio(event.data)

        elif event.type == EventType.VIDEO_FRAME and event.data is not None:
            self._send_video(event.data)

        elif event.type in (EventType.SYSTEM_START, EventType.SYSTEM_STOP):
            self._audio_send_json(_event_msg(event.type.value))

        with self._queue_lock:
            responses = list(self._response_queue)
            self._response_queue.clear()
        return responses

    # ── Отправка данных ───────────────────────────────────────────────────

    def send_raw_chunk(self, pcm_bytes: bytes) -> None:
        """Непрерывный стрим каждого чанка (без VAD) — для real-time мониторинга."""
        self._send_audio(pcm_bytes)

    def _send_audio(self, pcm_bytes: bytes) -> None:
        if not self._audio_connected or not self._audio_ws:
            return
        try:
            # Бинарная отправка — без base64, без JSON-обёртки
            self._audio_ws.send(pcm_bytes, opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception as exc:
            logger.warning("Аудио WS отправка: %s", exc)
            self._audio_connected = False

    def _send_video(self, frame) -> None:
        if not self._video_connected or not self._video_ws:
            return
        try:
            import cv2
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                self._video_ws.send(buf.tobytes(), opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception as exc:
            logger.warning("Видео WS отправка: %s", exc)
            self._video_connected = False

    def _audio_send_json(self, msg: str) -> None:
        if not self._audio_connected or not self._audio_ws:
            return
        try:
            self._audio_ws.send(msg)
        except Exception:
            pass

    # ── Аудио WebSocket (+ получение команд) ──────────────────────────────

    def _audio_loop(self) -> None:
        delay = self._reconnect_sec
        while True:
            try:
                ws = websocket.WebSocketApp(
                    self._audio_url,
                    on_open=self._audio_on_open,
                    on_message=self._on_command,
                    on_error=self._audio_on_error,
                    on_close=self._audio_on_close,
                )
                self._audio_ws = ws
                ws.run_forever(ping_interval=20, ping_timeout=10)
                delay = self._reconnect_sec
            except Exception as exc:
                logger.error("Аудио WS цикл: %s", exc)
            logger.info("Аудио WS реконнект через %.0f сек...", delay)
            time.sleep(delay)
            delay = min(delay * 2, 60.0)

    def _audio_on_open(self, ws) -> None:
        self._audio_connected = True
        self._audio_conn_count += 1
        reconnect = self._audio_conn_count > 1
        logger.info("Аудио WS %s: %s", "переподключён" if reconnect else "подключён", self._audio_url)
        if reconnect:
            threading.Thread(target=_play_beep, daemon=True).start()
        ws.send(_status_msg(time.time() - self._start_time))

    def _audio_on_close(self, ws, code, msg) -> None:
        self._audio_connected = False
        logger.warning("Аудио WS закрыт (code=%s)", code)

    def _audio_on_error(self, ws, err) -> None:
        self._audio_connected = False
        logger.warning("Аудио WS ошибка: %s", err)

    # ── Видео WebSocket ───────────────────────────────────────────────────

    def _video_loop(self) -> None:
        delay = self._reconnect_sec
        while True:
            try:
                ws = websocket.WebSocketApp(
                    self._video_url,
                    on_open=self._video_on_open,
                    on_error=self._video_on_error,
                    on_close=self._video_on_close,
                )
                self._video_ws = ws
                ws.run_forever(ping_interval=20, ping_timeout=10)
                delay = self._reconnect_sec
            except Exception as exc:
                logger.error("Видео WS цикл: %s", exc)
            logger.info("Видео WS реконнект через %.0f сек...", delay)
            time.sleep(delay)
            delay = min(delay * 2, 60.0)

    def _video_on_open(self, ws) -> None:
        self._video_connected = True
        self._video_conn_count += 1
        reconnect = self._video_conn_count > 1
        logger.info("Видео WS %s: %s", "переподключён" if reconnect else "подключён", self._video_url)
        if reconnect:
            threading.Thread(target=_play_beep, daemon=True).start()

    def _video_on_close(self, ws, code, msg) -> None:
        self._video_connected = False
        logger.warning("Видео WS закрыт (code=%s)", code)

    def _video_on_error(self, ws, err) -> None:
        self._video_connected = False
        logger.warning("Видео WS ошибка: %s", err)

    # ── Обработка входящих команд (на аудио-канале) ───────────────────────

    def _on_command(self, ws, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        response = self._parse_command(msg)
        if response:
            with self._queue_lock:
                self._response_queue.append(response)

    def _parse_command(self, msg: dict) -> Optional[AIResponse]:
        cmd = msg.get("type", "")
        if cmd == "speak":
            audio_b64 = msg.get("audio")
            audio_bytes = base64.b64decode(audio_b64) if audio_b64 else None
            return AIResponse(
                type=ResponseType.SPEAK,
                text=msg.get("text") if not audio_bytes else None,
                audio_bytes=audio_bytes,
                priority=msg.get("priority", 5),
            )
        elif cmd == "display":
            d = msg.get("display", {})
            return AIResponse(
                type=ResponseType.DISPLAY,
                display=DisplayCommand(
                    animation=d.get("animation", "idle"),
                    color=tuple(d.get("color", [0, 100, 255])),
                    duration_sec=d.get("duration_sec", 2.0),
                ),
            )
        elif cmd == "sms":
            return AIResponse(
                type=ResponseType.SMS_PARENT,
                text=msg.get("text", ""),
                phone=msg.get("phone"),
            )
        elif cmd == "idle":
            return AIResponse(type=ResponseType.IDLE)
        elif cmd == "ping":
            self._audio_send_json(_status_msg(time.time() - self._start_time))
            return None
        return None

    @property
    def audio_connected(self) -> bool:
        return self._audio_connected

    @property
    def video_connected(self) -> bool:
        return self._video_connected


# ─────────────────────────────────────────────────────────────────────────────
#  Пример минимального AI сервера (для тестирования)
# ─────────────────────────────────────────────────────────────────────────────

EXAMPLE_SERVER = '''
#!/usr/bin/env python3
"""
Пример AI сервера для Oiynup.
Установка: pip install websockets
Запуск:    python3 ai_server_example.py
"""
import asyncio, json, base64, websockets

async def handle(ws):
    print(f"[Oiynup] подключился: {ws.remote_address}")
    async for raw in ws:
        msg = json.loads(raw)
        t = msg.get("type")
        print(f"  ← {t}", msg.get("meta", {}).get("event", ""))

        if t == "audio":
            pcm = base64.b64decode(msg["data"])
            # TODO: распознать речь (Whisper, Vosk...)
            # TODO: обработать через LLM (Claude API...)
            # TODO: синтезировать ответ (Piper TTS...)
            await ws.send(json.dumps({
                "type": "speak",
                "text": "Я слышу тебя!",
            }))
            await ws.send(json.dumps({
                "type": "display",
                "display": {"animation": "happy", "color": [0,255,100], "duration_sec": 2},
            }))

        elif t == "video":
            # TODO: анализ кадра (YOLO, face detection...)
            pass

        elif t == "event":
            event = msg["meta"].get("event")
            if event == "system_start":
                await ws.send(json.dumps({"type": "display",
                    "display": {"animation": "rainbow", "duration_sec": 3}}))

asyncio.run(websockets.serve(handle, "0.0.0.0", 8765))
print("AI сервер запущен: ws://0.0.0.0:8765")
asyncio.get_event_loop().run_forever()
'''
