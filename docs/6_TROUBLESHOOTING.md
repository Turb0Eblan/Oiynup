# 6. Решение проблем

## SSH / Подключение

### `ssh: Connection refused`
SSH не запущен или RPi ещё загружается.
```bash
# Подождать 60-90 сек после включения
# Проверить что RPi живёт:
ping oiynup.local
# или
ping6 -I en6 fe80::XXXX:XXXX:XXXX:XXXX   # IPv6 через USB
```

### `ssh: Connection timed out` по USB
Mac не может найти RPi на USB.
```bash
# Проверить интерфейс
networksetup -listallhardwareports | grep -A2 Raspberry
# Должен показать "Raspberry Pi USB Gadget" со статусом active

# Установить IP на Mac
sudo ifconfig en6 10.55.0.2 netmask 255.255.255.0
ping 10.55.0.1

# Если RPi не получил IP — поискать по IPv6
dns-sd -q oiynup.local AAAA  # покажет FE80::... адрес
ssh -6 oiynup@fe80::XXXX%en6
```

### `Permission denied (publickey, password)`
Неверный пароль или пользователь.
```bash
# Пользователь — oiynup (не pi!)
ssh oiynup@10.55.0.1
```

---

## Аудио

### Нет звука из динамика
```bash
# Проверить ALSA устройства
aplay -l
# Должна быть карта googlevoicehat или hifiberry

# Тест напрямую
speaker-test -t sine -f 1000 -l1 -s1

# Проверить /boot/firmware/config.txt
grep -E "i2s|googlevoice|hifiberry" /boot/firmware/config.txt
# Должно быть:
# dtparam=i2s=on
# dtoverlay=googlevoicehat-soundcard
```

### Микрофон не пишет / уровень 0%
```bash
# Проверить устройства записи
arecord -l

# Тест записи
arecord -D hw:0,0 -c2 -r16000 -f S32_LE -d3 /tmp/test.wav
aplay /tmp/test.wav

# Проверить подключение INMP441:
# SD → GPIO20 (пин 38)
# SCK → GPIO18 (пин 12)
# WS  → GPIO19 (пин 35)
# L/R → GND (пин 6)
```

---

## Камера

### `No cameras available`
```bash
# Включить камеру
sudo raspi-config
# Interface Options → Camera → Enable → Reboot

# Проверить
libcamera-hello --list-cameras
libcamera-hello --timeout 3000

# Проверить ленту:
# Контакты смотрят К плате RPi
# Синяя сторона ленты — наружу
```

---

## GSM / SIM900

### SIM900 не отвечает на AT команды
```bash
# Проверить UART
ls /dev/ttyS0

# Убедиться что serial console убран из cmdline.txt
grep "serial0" /boot/firmware/cmdline.txt
# Не должно быть "console=serial0,..."

# Проверить что Bluetooth отключён (освободить UART)
grep "disable-bt" /boot/firmware/config.txt

# Тест AT команды вручную
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyS0', 9600, timeout=3)
s.write(b'AT\r\n')
time.sleep(1)
print(s.read_all())
s.close()
"
# Должно вернуть b'AT\r\r\nOK\r\n'
```

### `No signal` (99/31)
- Проверить SIM-карту (вставлена? PIN отключён?)
- Проверить питание SIM900 (нужен **отдельный БП 5V/2A**)
- Переместить устройство ближе к окну

---

## LED матрица

### Матрица не светится или мигает хаотично
```bash
# Нужны права root для GPIO
sudo python3 scripts/test_hardware.py --led

# Проверить резистор 300 Ом в линии DIN!

# Проверить core_freq в config.txt
grep "core_freq" /boot/firmware/config.txt
# Должно быть:
# core_freq=500
# core_freq_min=500
```

---

## Система

### `ModuleNotFoundError`
```bash
# Установить недостающий пакет
pip3 install --break-system-packages <package_name>

# Проверить все пакеты
pip3 list | grep -E "pyaudio|pyserial|RPi|rpi_ws|numpy|opencv"
```

### Система зависает / высокая нагрузка
```bash
# Посмотреть нагрузку
htop

# Посмотреть логи
journalctl -u oiynup -n 50

# Перезапустить
sudo systemctl restart oiynup
```

### RPi не загружается (нет зелёного LED)
Скорее всего повреждён образ на SD карте или конфликт в config.txt.
- Перезаписать SD карту через Raspberry Pi Imager
- Проверить config.txt на лишние/неверные строки

---

## panel.py (панель управления)

### Браузер не открывается
```bash
# Открыть вручную
open http://localhost:7777
```

### `flask not found`
```bash
pip3 install flask paramiko
```

### Крашится с ошибкой tkinter/Tk
Старая версия (tkinter): `python3 panel.py` → смотреть что запустилась новая версия (Flask).  
Если крашится — убедись что файл panel.py обновлён (должен импортировать flask, не tkinter).

---

## Полезные команды

```bash
# Статус всех сервисов
systemctl status oiynup

# Сеть
ip addr show
nmcli device status

# Диск
df -h /

# Температура RPi
vcgencmd measure_temp

# Частота CPU
vcgencmd measure_clock arm

# GPIO состояние
raspi-gpio get

# Аудио устройства
aplay -l && arecord -l

# I2C устройства
i2cdetect -y 1
```
