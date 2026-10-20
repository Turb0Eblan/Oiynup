# Oiynup — Детское AI-устройство

> Образовательное устройство для детей на базе Raspberry Pi Zero 2 W  
> с камерой, микрофоном, динамиком, RGB-матрицей и GSM-связью с родителями.

---

## Быстрый старт

```bash
# 1. Запустить панель управления (на Mac)
python3 panel.py
# Открывает браузер на http://localhost:7777

# 2. Подключиться к RPi по SSH (USB кабель)
ssh oiynup@10.55.0.1

# 3. Запустить систему на RPi
sudo python3 /home/oiynup/oiynup/src/main.py --debug

# 4. Задеплоить изменения кода
./deploy.sh
```

---

## Документация

| Файл | Содержание |
|------|-----------|
| [docs/1_HARDWARE.md](docs/1_HARDWARE.md) | Компоненты, схема подключения, пайка |
| [docs/2_SETUP.md](docs/2_SETUP.md) | Установка RPi OS, настройка системы |
| [docs/3_SOFTWARE.md](docs/3_SOFTWARE.md) | Архитектура кода, модули |
| [docs/4_AI_INTEGRATION.md](docs/4_AI_INTEGRATION.md) | Интеграция AI-системы (для коллег) |
| [docs/5_PANEL.md](docs/5_PANEL.md) | Панель управления panel.py |
| [docs/6_TROUBLESHOOTING.md](docs/6_TROUBLESHOOTING.md) | Решение типичных проблем |
| [hardware/PIN_REFERENCE.md](hardware/PIN_REFERENCE.md) | Справочник пинов (для монтажа) |

---

## Состав железа

| Компонент | Модель | Назначение |
|-----------|--------|-----------|
| Процессор | Raspberry Pi Zero 2 W | Основной компьютер |
| Камера | Camera Module v2 | Видео для AI |
| Микрофон | INMP441 | Запись голоса (I2S) |
| Усилитель | MAX98357 | Вывод звука (I2S) |
| GSM модуль | SIM900 | SMS родителям (UART) |
| LED матрица | WS2812B 8×8 | Визуальная обратная связь |

---

## Структура проекта

```
Oiynup/
├── panel.py                  # Веб-панель управления (запускать на Mac)
├── deploy.sh                 # Скрипт деплоя кода на RPi
├── requirements.txt          # Python зависимости
│
├── src/                      # Исходный код устройства
│   ├── main.py               # Точка входа — главный оркестратор
│   ├── config.py             # Все настройки (пины, порты, параметры)
│   ├── ai_interface.py       # ← ИНТЕРФЕЙС ДЛЯ AI-КОМАНДЫ
│   ├── camera.py             # Модуль камеры
│   ├── audio_input.py        # Микрофон INMP441
│   ├── audio_output.py       # Динамик MAX98357
│   ├── gsm.py                # GSM SIM900
│   └── led_matrix.py         # RGB матрица WS2812B
│
├── docs/                     # Документация
├── hardware/                 # Схемы подключения
└── scripts/
    ├── setup_rpi.sh          # Первоначальная настройка RPi
    └── test_hardware.py      # Тест каждого модуля отдельно
```

---

## Команда

- **Железо и система** — подключение, настройка RPi, базовый код
- **AI-команда** — реализация `BaseAIBackend` в `src/ai_interface.py`

---

## Версия

| Параметр | Значение |
|----------|---------|
| RPi OS | Bookworm (Debian 13) 64-bit |
| Python | 3.13 |
| Дата | 2026-05-12 |
