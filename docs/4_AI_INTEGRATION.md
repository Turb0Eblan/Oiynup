# 4. Интеграция AI-системы

> **Этот документ для AI-команды.**  
> Здесь описано как подключить свою AI-систему к устройству.

---

## Концепция

Устройство собирает данные (аудио, видео) и передаёт их в AI.  
AI анализирует данные и возвращает команды (говорить, показать анимацию, отправить SMS).

```
Ребёнок говорит → INMP441 → RPi → [ваша AI] → RPi → MAX98357 → Ребёнок слышит ответ
Камера видит    → Camera  → RPi → [ваша AI] → RPi → LED матрица → эмоция
```

---

## Как подключить свою AI — 3 шага

### Шаг 1 — Создать класс

```python
# my_ai.py — ваш файл

from ai_interface import BaseAIBackend, DeviceEvent, EventType, AIResponse, ResponseType, DisplayCommand

class MyAI(BaseAIBackend):

    def on_start(self):
        """Вызывается один раз при запуске устройства."""
        # Загрузите свои модели здесь
        self.stt = load_speech_to_text_model()
        self.llm = load_language_model()
        self.tts = load_text_to_speech_model()

    def on_stop(self):
        """Вызывается при выключении."""
        pass

    def process_event(self, event: DeviceEvent) -> list[AIResponse]:
        """Главная функция — обработка событий от устройства."""

        if event.type == EventType.AUDIO_CHUNK:
            return self._handle_audio(event)

        if event.type == EventType.VIDEO_FRAME:
            return self._handle_video(event)

        if event.type == EventType.SYSTEM_START:
            return [AIResponse(
                type=ResponseType.SPEAK,
                text="Сәлем! Мен Ойнаппын!",
            )]

        return []

    def _handle_audio(self, event):
        # event.data = bytes, PCM 16-bit mono 16kHz
        text = self.stt.transcribe(event.data)
        if not text:
            return []

        answer = self.llm.respond(text)
        audio  = self.tts.synthesize(answer)

        return [
            AIResponse(
                type=ResponseType.DISPLAY,
                display=DisplayCommand(animation="thinking"),
            ),
            AIResponse(
                type=ResponseType.SPEAK,
                audio_bytes=audio,  # готовый WAV
                priority=3,
            ),
            AIResponse(
                type=ResponseType.DISPLAY,
                display=DisplayCommand(animation="happy", duration_sec=3),
            ),
        ]

    def _handle_video(self, event):
        # event.data = numpy array, BGR, shape (H, W, 3)
        # Анализ сцены, распознавание лиц, etc.
        return []
```

### Шаг 2 — Подключить в main.py

```python
# src/main.py — найти строку:
ai_backend = MockAIBackend()

# Заменить на:
import sys
sys.path.insert(0, '/home/oiynup/my_ai')  # путь к вашему файлу
from my_ai import MyAI
ai_backend = MyAI()
```

### Шаг 3 — Задеплоить и запустить

```bash
# С Mac
./deploy.sh
ssh oiynup@10.55.0.1 "sudo systemctl restart oiynup"
```

---

## Типы событий (что AI получает)

### `EventType.AUDIO_CHUNK`
```python
event.type = EventType.AUDIO_CHUNK
event.data = bytes           # PCM 16-bit signed, Little Endian
event.metadata = {
    "sample_rate": 16000,   # Гц
    "channels":    1,        # моно
    "format":      "pcm_s16le",
}
```
Отправляется когда детектор речи (VAD) зафиксировал законченную фразу.  
Конвертация в numpy: `np.frombuffer(event.data, dtype=np.int16)`

### `EventType.VIDEO_FRAME`
```python
event.type = EventType.VIDEO_FRAME
event.data = np.ndarray      # shape (720, 1280, 3), dtype uint8, BGR
event.metadata = {
    "resolution": (1280, 720),
    "format":     "bgr888",
}
```
Отправляется каждые N секунд (config.camera.capture_interval_sec = 5.0).

### `EventType.SYSTEM_START` / `EventType.SYSTEM_STOP`
```python
event.type = EventType.SYSTEM_START
event.data = None
```

---

## Типы ответов (что AI возвращает)

### `ResponseType.SPEAK` — произнести текст или аудио
```python
# Вариант 1: текст → TTS через espeak-ng на устройстве
AIResponse(
    type=ResponseType.SPEAK,
    text="Дұрыс жауап!",      # TTS на устройстве
    priority=3,                # 1=срочно, 10=фон
)

# Вариант 2: готовый WAV от вашего TTS
AIResponse(
    type=ResponseType.SPEAK,
    audio_bytes=wav_bytes,     # bytes, WAV формат
    priority=3,
)
```

### `ResponseType.DISPLAY` — анимация на RGB матрице
```python
AIResponse(
    type=ResponseType.DISPLAY,
    display=DisplayCommand(
        animation="correct",           # имя анимации
        color=(0, 255, 100),           # RGB цвет
        duration_sec=2.0,              # 0 = бесконечно
    ),
)
```

Доступные анимации:
| Имя | Описание |
|-----|---------|
| `idle` | Спокойное синее пульсирование |
| `listening` | Голубое мерцание — слушаем |
| `thinking` | Вращающийся жёлтый — думаем |
| `happy` | Зелёные огни — радость |
| `correct` | Вспышка зелёного — правильно! |
| `wrong` | Вспышка красного — попробуй ещё |
| `rainbow` | Радуга |

### `ResponseType.SMS_PARENT` — SMS родителю
```python
AIResponse(
    type=ResponseType.SMS_PARENT,
    text="Ойнап: ребёнок решил задачу! 🎉",
)
```

### `ResponseType.LESSON_UPDATE` — данные урока
```python
AIResponse(
    type=ResponseType.LESSON_UPDATE,
    lesson_data={
        "topic":    "Числа 1-10",
        "progress": 0.7,
        "score":    85,
    },
)
```

---

## Полный пример диалога

```python
def process_event(self, event):
    if event.type != EventType.AUDIO_CHUNK:
        return []

    # 1. Показываем что слушаем
    responses = [
        AIResponse(type=ResponseType.DISPLAY,
                   display=DisplayCommand(animation="listening", duration_sec=0))
    ]

    # 2. Распознаём речь
    text = self.stt.transcribe(event.data)
    if not text:
        return [AIResponse(type=ResponseType.DISPLAY,
                           display=DisplayCommand(animation="idle"))]

    # 3. Показываем что думаем
    responses.append(
        AIResponse(type=ResponseType.DISPLAY,
                   display=DisplayCommand(animation="thinking"))
    )

    # 4. Генерируем ответ
    answer, is_correct = self.lesson.check_answer(text)

    # 5. Анимация результата
    responses.append(
        AIResponse(type=ResponseType.DISPLAY,
                   display=DisplayCommand(
                       animation="correct" if is_correct else "wrong",
                       duration_sec=2
                   ))
    )

    # 6. Произносим ответ
    responses.append(
        AIResponse(type=ResponseType.SPEAK, text=answer, priority=2)
    )

    # 7. SMS родителю при хорошем результате
    if is_correct and self.lesson.milestone_reached():
        responses.append(
            AIResponse(type=ResponseType.SMS_PARENT,
                       text=f"Ойнап: {self.child_name} прошёл тему «{self.lesson.topic}»! 🌟")
        )

    return responses
```

---

## Метаданные события (аудио)

```python
# Конвертация PCM bytes → numpy float32 (для нейросетей)
import numpy as np

def bytes_to_float(pcm_bytes):
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0
    # shape: (N,), dtype: float32, range: [-1.0, 1.0]

# Конвертация для librosa/whisper
audio_float = bytes_to_float(event.data)
# sample_rate = event.metadata["sample_rate"]  # 16000
```
