# 7. Протокол стриминга — Oiynup WebSocket Protocol

**Версия:** 1.0  
**Дата:** 2026-05-13  
**Транспорт:** WebSocket (RFC 6455)  
**Формат:** JSON + бинарные данные в Base64

---

## Архитектура

```
┌─────────────────────────────────┐         ┌──────────────────────────────┐
│        Oiynup Device (RPi)      │         │      AI Сервер               │
│                                 │         │  (любой язык/платформа)      │
│  Камера ──→ ┐                   │   WS    │                              │
│  Микрофон ─→┤ WebSocketAI  ────────────→  │  Whisper (STT)               │
│  Статус ──→ ┘ Backend           │         │  Claude / GPT (LLM)          │
│                                 │   WS    │  Piper / ElevenLabs (TTS)    │
│  Динамик ←── ┐                  │ ←──────── │                              │
│  LED матрица←┤ команды          │         │                              │
│  GSM SMS ←── ┘                  │         │                              │
└─────────────────────────────────┘         └──────────────────────────────┘

RPi = WebSocket CLIENT
AI Сервер = WebSocket SERVER (порт 8765 по умолчанию)
```

**RPi всегда инициирует подключение.** При обрыве — автоматически переподключается каждые 5 секунд.

---

## Подключение к WebSocket серверу

```python
# В src/main.py — заменить MockAIBackend на WebSocketAIBackend:
from streaming import WebSocketAIBackend

backend = WebSocketAIBackend(server_url="ws://192.168.1.100:8765")
device = OiynupDevice(cfg=config, ai_backend=backend)
device.run_forever()
```

---

## Формат сообщения

Все сообщения — **JSON строки** в кодировке UTF-8.

```json
{
  "type":      "тип_сообщения",
  "id":        "a3f2b1c0",
  "timestamp": 1715596800.123,
  "data":      "base64_данные_или_null",
  "meta":      { "доп_поля": "..." }
}
```

| Поле | Тип | Описание |
|------|-----|---------|
| `type` | string | Тип сообщения (см. ниже) |
| `id` | string | Уникальный ID (8 символов, для логов) |
| `timestamp` | float | Unix timestamp (секунды с дробной частью) |
| `data` | string\|null | Base64 бинарные данные (аудио/видео) |
| `meta` | object | Дополнительные метаданные |

---

## Сообщения RPi → Сервер

### `audio` — аудио фрейм

Отправляется каждый раз когда VAD обнаруживает речь.

```json
{
  "type": "audio",
  "id": "a3f2b1c0",
  "timestamp": 1715596800.123,
  "data": "BASE64_PCM_BYTES",
  "meta": {
    "sample_rate": 16000,
    "channels": 1,
    "format": "pcm_s16le",
    "duration_ms": 1500
  }
}
```

| Параметр | Значение |
|---------|---------|
| Формат | PCM Signed 16-bit Little Endian |
| Частота | 16000 Hz (16kHz) |
| Каналы | 1 (моно) |
| Размер | Переменный (зависит от длины фразы) |

**Декодирование на сервере:**
```python
import base64, numpy as np

data = base64.b64decode(msg["data"])
samples = np.frombuffer(data, dtype=np.int16)
# sample_rate = 16000
# → подать в Whisper, Vosk и т.д.
```

---

### `video` — кадр с камеры

Отправляется каждые N секунд (config.camera.capture_interval_sec, по умолчанию 5 сек).

```json
{
  "type": "video",
  "id": "b7c3d2e1",
  "timestamp": 1715596805.000,
  "data": "BASE64_JPEG_BYTES",
  "meta": {
    "format": "jpeg",
    "resolution": [1280, 720],
    "quality": 70
  }
}
```

**Декодирование на сервере:**
```python
import base64, cv2, numpy as np

data = base64.b64decode(msg["data"])
arr = np.frombuffer(data, dtype=np.uint8)
frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
# frame: numpy array BGR (H, W, 3)
# → подать в YOLO, face detection, GPT-4V и т.д.
```

---

### `status` — статус устройства

Отправляется при подключении и в ответ на `ping`.

```json
{
  "type": "status",
  "id": "c1d4e5f6",
  "timestamp": 1715596800.000,
  "data": null,
  "meta": {
    "device": "oiynup",
    "uptime_sec": 3600.5,
    "wifi_ip": "192.168.1.42"
  }
}
```

---

### `event` — системное событие

```json
{
  "type": "event",
  "id": "d2e5f6a7",
  "timestamp": 1715596800.000,
  "data": null,
  "meta": {
    "event": "system_start"
  }
}
```

| `event` | Когда |
|---------|-------|
| `system_start` | Устройство включено |
| `system_stop` | Устройство выключается |

---

## Команды Сервер → RPi

### `speak` — произнести текст или аудио

```json
{
  "type": "speak",
  "text": "Дұрыс жауап! Молодец!",
  "priority": 3
}
```

Или с готовым аудио (WAV байты в Base64):
```json
{
  "type": "speak",
  "audio": "BASE64_WAV_BYTES",
  "priority": 1
}
```

| `priority` | Значение |
|-----------|---------|
| 1 | Срочно — прервать текущее |
| 3 | Обычный ответ |
| 5 | Фоновый |
| 10 | Самый низкий |

---

### `display` — анимация на RGB матрице

```json
{
  "type": "display",
  "display": {
    "animation": "correct",
    "color": [0, 255, 100],
    "duration_sec": 2.0
  }
}
```

| `animation` | Описание |
|------------|---------|
| `idle` | Спокойное синее пульсирование |
| `listening` | Голубое мерцание — слушаем |
| `thinking` | Вращающийся жёлтый — думаем |
| `happy` | Зелёные огни — радость |
| `correct` | Вспышка зелёного — правильно! |
| `wrong` | Вспышка красного — попробуй ещё |
| `rainbow` | Радуга |

---

### `sms` — отправить SMS родителю

```json
{
  "type": "sms",
  "text": "Ойнап: ребёнок решил тему «Числа 1-10»! 🌟"
}
```

Номер берётся из `config.gsm.parent_phone`. Поддерживает кириллицу.

---

### `ping` — проверка связи

```json
{ "type": "ping" }
```

RPi отвечает сообщением `status`.

---

### `idle` — ничего не делать

```json
{ "type": "idle" }
```

---

## Пример полного диалога

```
RPi     → Сервер:   {"type":"event","meta":{"event":"system_start"}}
Сервер  → RPi:      {"type":"display","display":{"animation":"rainbow","duration_sec":3}}

RPi     → Сервер:   {"type":"audio","data":"BASE64...","meta":{"sample_rate":16000,...}}
                    (ребёнок сказал "Сколько будет два плюс три?")

Сервер  → RPi:      {"type":"display","display":{"animation":"thinking"}}
                    (сервер думает...)

Сервер  → RPi:      {"type":"speak","text":"Два плюс три равно пять!","priority":3}
Сервер  → RPi:      {"type":"display","display":{"animation":"happy","duration_sec":2}}

RPi     → Сервер:   {"type":"audio","data":"BASE64..."}
                    (ребёнок сказал "Пять!")

Сервер  → RPi:      {"type":"speak","text":"Правильно! Молодец!","priority":2}
Сервер  → RPi:      {"type":"display","display":{"animation":"correct","duration_sec":2}}
Сервер  → RPi:      {"type":"sms","text":"Ойнап: ребёнок решил задачу!"}
```

---

## Быстрый старт для AI-команды

### 1. Установить зависимости

```bash
pip install websockets websocket-client
```

### 2. Запустить минимальный тестовый сервер

```bash
python3 -c "
import asyncio, json, base64, websockets

async def handle(ws):
    print('Oiynup подключился:', ws.remote_address)
    async for raw in ws:
        msg = json.loads(raw)
        print('←', msg['type'], msg.get('meta',{}))
        if msg['type'] == 'audio':
            await ws.send(json.dumps({'type':'speak','text':'Привет!'}))
            await ws.send(json.dumps({'type':'display','display':{'animation':'happy','duration_sec':2}}))

async def main():
    async with websockets.serve(handle, '0.0.0.0', 8765):
        print('Сервер: ws://0.0.0.0:8765')
        await asyncio.Future()

asyncio.run(main())
"
```

### 3. Подключить RPi к серверу

```python
# src/main.py
from streaming import WebSocketAIBackend

backend = WebSocketAIBackend("ws://IP_СЕРВЕРА:8765")
device = OiynupDevice(cfg=config, ai_backend=backend)
device.run_forever()
```

---

## Параметры потоков

| Поток | Формат | Частота | Размер пакета |
|-------|--------|---------|--------------|
| Аудио | PCM S16LE mono | При обнаружении речи | ~10-50 КБ |
| Видео | JPEG quality=70 | Каждые 5 сек | ~30-80 КБ |
| Статус | JSON | При подключении + по запросу | < 1 КБ |

---

## Установка зависимостей на RPi

```bash
pip3 install --break-system-packages websocket-client
```

---

## История изменений

| Дата | Версия | Изменение |
|------|--------|-----------|
| 2026-05-13 | 1.0 | Начальная версия протокола |
