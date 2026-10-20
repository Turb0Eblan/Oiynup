# 2. Настройка — от нуля до рабочей системы

## Шаг 1 — Запись RPi OS на SD карту

1. Скачай **Raspberry Pi Imager** → [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Выбери устройство: `Raspberry Pi Zero 2 W`
3. Выбери OS: `Raspberry Pi OS Lite (64-bit)` (без рабочего стола)
4. Нажми **Edit Settings** и заполни:

```
Hostname:  oiynup
Username:  oiynup
Password:  (свой пароль)
WiFi SSID: (имя сети)
WiFi Pass: (пароль сети)
Country:   KZ
SSH:       Enable ✓
```

5. Записать образ (~5 минут)

---

## Шаг 2 — Первый запуск

```bash
# Вставить SD карту, подать питание
# Подождать 2 минуты

# Найти RPi в сети
ping oiynup.local

# Подключиться по SSH
ssh oiynup@oiynup.local
# или через USB:
ssh oiynup@10.55.0.1
```

---

## Шаг 3 — Настройка интерфейсов

```bash
sudo raspi-config
```

Включить:
- **Interface Options → Camera** → Enable
- **Interface Options → Serial Port** → Shell: No, Hardware: Yes

---

## Шаг 4 — Автоматическая установка

```bash
# На RPi:
sudo bash /boot/firmware/oiynup_setup.sh
```

Скрипт устанавливает:
- Системные пакеты (python3, portaudio, espeak-ng, git, rsync...)
- Python пакеты (pyaudio, pyserial, RPi.GPIO, rpi_ws281x, opencv...)
- Настраивает WiFi и USB OTG (10.55.0.1)
- Создаёт systemd сервис `oiynup`

---

## Шаг 5 — Деплой кода

**С Mac через панель управления:**
```bash
python3 panel.py
# Вкладка "Деплой" → "Загрузить код"
```

**Или вручную:**
```bash
./deploy.sh
```

---

## Шаг 6 — Проверка

```bash
# Запустить тест железа
sudo python3 ~/oiynup/scripts/test_hardware.py --all

# Запустить систему вручную
sudo python3 ~/oiynup/src/main.py --debug

# Запустить как сервис
sudo systemctl start oiynup
sudo systemctl status oiynup
```

---

## Подключение к RPi

### По USB (без WiFi — везде работает)
```bash
# RPi подключён USB-кабелем к Mac (разъём USB, не PWR)
ssh oiynup@10.55.0.1

# Если 10.55.0.1 не работает — IPv6:
ssh -6 oiynup@fe80::XXXX:XXXX:XXXX:XXXX%en6
# IPv6 адрес найти: dns-sd -q oiynup.local AAAA
```

### По WiFi
```bash
ssh oiynup@oiynup.local
# или
ssh oiynup@<IP из роутера>
```

---

## Деплой кода на RPi (рабочий процесс)

```bash
# 1. Изменил код на Mac в VS Code
# 2. Подключил USB кабель к RPi
# 3. Задеплоил:
./deploy.sh
# или через панель: python3 panel.py → Деплой

# 4. Смотришь логи:
ssh oiynup@10.55.0.1 "journalctl -f -u oiynup"
```

---

## Автозапуск при включении

```bash
sudo systemctl enable oiynup
sudo reboot
```

После перезагрузки система стартует автоматически.

---

## Добавить новую WiFi сеть

```bash
# На RPi:
sudo nmcli device wifi connect "Название_сети" password "пароль"

# Или отредактировать на SD карте (пока RPi выключен):
# /boot/firmware/network-config → раздел access-points
```
