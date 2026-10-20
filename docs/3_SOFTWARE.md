# 3. Программная архитектура

## Обзор системы

```
┌─────────────────────────────────────────────────────────────┐
│                    Oiynup Device (RPi)                      │
│                                                             │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  │
│  │ camera.py│  │audio_input│  │audio_out │  │  gsm.py  │  │
│  │ Camera   │  │  INMP441  │  │ MAX98357 │  │  SIM900  │  │
│  └────┬─────┘  └─────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │               │              │              │        │
│       └───────────────┴──────────────┴──────────────┘       │
│                               │                             │
│                    ┌──────────▼──────────┐                  │
│                    │      main.py        │                  │
│                    │  OiynupDevice       │                  │
│                    │  (оркестратор)      │                  │
│                    └──────────┬──────────┘                  │
│                               │                             │
│                    ┌──────────▼──────────┐                  │
│                    │   ai_interface.py   │                  │
│                    │   BaseAIBackend     │◄── AI команда    │
│                    └─────────────────────┘                  │
│                                                             │
│  ┌────────────┐                                             │
│  │led_matrix  │◄── Анимации от AI                          │
│  │  WS2812B   │                                             │
│  └────────────┘                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Файлы и их роли

### `config.py` — Центральная конфигурация
Все настройки в одном месте: GPIO пины, ALSA устройства, параметры аудио, номер телефона.

```python
from config import config

# Изменить номер родителя
config.gsm.parent_phone = "+77001234567"

# Изменить яркость матрицы
config.led.brightness = 0.5

# Изменить язык
config.language = "kk"  # "kk", "ru", "en"
```

---

### `main.py` — Главный оркестратор
Запускает все модули, подписывает их на события, передаёт события в AI.

```python
# Запуск с заглушкой AI
python3 src/main.py --debug

# Запуск со своим AI бэкендом
from my_ai import MyAI
device = OiynupDevice(cfg=config, ai_backend=MyAI())
device.run_forever()
```

**Поток данных:**
```
INMP441 → AudioInput → phrase_callback → main.py → AI.process_event()
Camera  → CameraModule → frame_callback → main.py → AI.process_event()

AI.process_event() → AIResponse → main.py →
  SPEAK   → AudioOutput → MAX98357 → Динамик
  DISPLAY → LedMatrix   → WS2812B
  SMS     → GsmModule   → SIM900 → Родитель
```

---

### `camera.py` — Модуль камеры
```python
from camera import CameraModule
from config import config

cam = CameraModule(config.camera)
cam.start()

# Получить один кадр (numpy BGR)
frame = cam.capture_frame()

# Получить JPEG байты
jpeg = cam.capture_jpeg(quality=85)

# Подписаться на кадры для AI
cam.add_frame_callback(lambda frame: ...)

cam.stop()
```

**Параметры** (`config.camera`):
- `resolution` — разрешение (1280×720)
- `capture_interval_sec` — интервал отправки кадров в AI (5.0 сек)

---

### `audio_input.py` — Микрофон INMP441
```python
from audio_input import AudioInputModule

mic = AudioInputModule(config.audio_input)

# Получить законченную фразу (VAD)
mic.add_phrase_callback(lambda pcm_bytes: ...)

# Получить каждый chunk (стриминг)
mic.add_chunk_callback(lambda chunk: ...)

mic.start()
```

**VAD (Voice Activity Detection):**  
Встроенный детектор речи на основе RMS. Параметры:
- `silence_threshold` — порог тишины (0.01)
- `silence_duration_sec` — пауза = конец фразы (1.5 сек)

**Формат аудио:** PCM 16-bit mono, 16000 Hz

---

### `audio_output.py` — Динамик MAX98357
```python
from audio_output import AudioOutputModule

speaker = AudioOutputModule(config.audio_output)
speaker.start()

# TTS через espeak-ng
speaker.speak("Привет!", language="ru", priority=3)

# Воспроизвести готовый WAV
speaker.play_bytes(wav_bytes, priority=1)

# Воспроизвести файл
speaker.play_file("/path/to/file.wav")
```

**Очередь с приоритетом:** priority=1 (высший) … 10 (низший)

---

### `gsm.py` — Модуль SIM900
```python
from gsm import GsmModule

gsm = GsmModule(config.gsm)
gsm.start()

# Отправить SMS
gsm.send_sms("Текст сообщения", phone="+77001234567")

# Стандартные уведомления
gsm.send_parent_alert("system_start")   # RPi включён
gsm.send_parent_alert("system_stop")    # RPi выключается
gsm.send_parent_alert("child_crying")   # ребёнок плачет

# Уровень сигнала (0-31, 99=нет сигнала)
signal = gsm.get_signal_strength()
```

**Поддержка кириллицы:** SMS кодируются в UCS2 (Unicode), поддерживает казахский и русский.

---

### `led_matrix.py` — RGB матрица WS2812B
```python
from led_matrix import LedMatrix

led = LedMatrix(config.led)
led.start()

# Запустить анимацию
led.animation("happy",    color=(0, 255, 100), duration_sec=2)
led.animation("thinking", color=(255, 200, 0))   # бесконечно
led.animation("idle")     # пульсирующий синий
led.animation("correct")  # вспышка зелёного
led.animation("wrong")    # вспышка красного
led.animation("rainbow")
led.animation("listening")

# Заполнить одним цветом
led.fill(r=255, g=0, b=0)

led.stop()
```

**Доступные анимации:** `idle`, `happy`, `thinking`, `correct`, `wrong`, `rainbow`, `listening`

---

## Установленные зависимости RPi

| Пакет | Версия | Зачем |
|-------|--------|-------|
| python3-picamera2 | — | Камера (apt) |
| pyaudio | 0.2.14 | Аудио I/O |
| pyserial | 3.5 | UART для SIM900 |
| RPi.GPIO | 0.7.1 | GPIO управление |
| rpi_ws281x | 5.0.0 | WS2812B LED |
| numpy | 2.2.4 | Обработка аудио |
| opencv-python-headless | 4.13 | Обработка кадров |
| espeak-ng | — | TTS (apt) |

---

## Запуск и управление

```bash
# Вручную (с логами в терминал)
sudo python3 ~/oiynup/src/main.py --debug

# Через systemd
sudo systemctl start   oiynup
sudo systemctl stop    oiynup
sudo systemctl restart oiynup
sudo systemctl status  oiynup

# Просмотр логов
journalctl -u oiynup -f
journalctl -u oiynup -n 100 --no-pager

# Автозапуск при загрузке
sudo systemctl enable oiynup
```
