#!/bin/bash
# Oiynup — скрипт настройки Raspberry Pi Zero 2 W
# INMP441 (I2S mic) + MAX98357 (I2S speaker) + SIM900 (UART) + WS2812B (PWM)
#
# Запустить один раз после чистой установки RPi OS Bullseye/Bookworm:
#   sudo bash setup_rpi.sh

set -e
echo "=== Oiynup: настройка системы ==="

# ---------------------------------------------------------------------------
# 1. Системные пакеты
# ---------------------------------------------------------------------------
apt-get update
apt-get install -y \
    python3-pip \
    python3-dev \
    python3-numpy \
    python3-picamera2 \
    portaudio19-dev \
    espeak-ng \
    alsa-utils \
    libatlas-base-dev \
    libjpeg-dev \
    libopenjp2-7 \
    git

# ---------------------------------------------------------------------------
# 2. Python пакеты
# ---------------------------------------------------------------------------
pip3 install --break-system-packages \
    pyaudio \
    pyserial \
    RPi.GPIO \
    rpi_ws281x \
    numpy \
    opencv-python-headless

# ---------------------------------------------------------------------------
# 3. /boot/config.txt
# ---------------------------------------------------------------------------
CONFIG_FILE="/boot/config.txt"
[ -f /boot/firmware/config.txt ] && CONFIG_FILE="/boot/firmware/config.txt"

echo ""
echo "=== Настройка $CONFIG_FILE ==="

# I2S интерфейс (нужен и для INMP441, и для MAX98357)
grep -q "dtparam=i2s=on" "$CONFIG_FILE" \
    || echo "dtparam=i2s=on" >> "$CONFIG_FILE"

# -------------------------------------------------------------------
# Overlay для полного дуплекса I2S:
# googlevoicehat-soundcard — поддерживает одновременно
# вход (GPIO20, PCM_DIN) и выход (GPIO21, PCM_DOUT)
# на одном I2S интерфейсе.
# -------------------------------------------------------------------
# Удаляем старый hifiberry-dac если был
sed -i '/dtoverlay=hifiberry-dac/d' "$CONFIG_FILE"

grep -q "dtoverlay=googlevoicehat-soundcard" "$CONFIG_FILE" \
    || echo "dtoverlay=googlevoicehat-soundcard" >> "$CONFIG_FILE"

# UART для SIM900: отключаем BT, освобождаем /dev/ttyS0 (GPIO14/15)
grep -q "dtoverlay=disable-bt" "$CONFIG_FILE" \
    || echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"
grep -q "enable_uart=1" "$CONFIG_FILE" \
    || echo "enable_uart=1" >> "$CONFIG_FILE"

# PWM для WS2812B (GPIO13 = PWM1) — core_freq должна быть фиксирована
grep -q "core_freq=500" "$CONFIG_FILE" \
    || echo "core_freq=500" >> "$CONFIG_FILE"
grep -q "core_freq_min=500" "$CONFIG_FILE" \
    || echo "core_freq_min=500" >> "$CONFIG_FILE"

# Камера
grep -q "start_x=1" "$CONFIG_FILE" \
    || echo "start_x=1" >> "$CONFIG_FILE"
grep -q "gpu_mem=128" "$CONFIG_FILE" \
    || echo "gpu_mem=128" >> "$CONFIG_FILE"

echo "Итог $CONFIG_FILE (последние 12 строк):"
tail -12 "$CONFIG_FILE"

# ---------------------------------------------------------------------------
# 4. Убрать serial console с UART (нужен для SIM900)
# ---------------------------------------------------------------------------
CMDLINE="/boot/cmdline.txt"
[ -f /boot/firmware/cmdline.txt ] && CMDLINE="/boot/firmware/cmdline.txt"

if grep -q "console=serial0" "$CMDLINE"; then
    sed -i 's/console=serial0,[0-9]* //g' "$CMDLINE"
    echo "Serial console убран из $CMDLINE — UART свободен для SIM900"
fi

# ---------------------------------------------------------------------------
# 5. ALSA конфигурация для полного дуплекса
# ---------------------------------------------------------------------------
# googlevoicehat-soundcard регистрирует одно устройство:
#   card 0: вход  (INMP441) + выход (MAX98357)
# Команды для проверки после перезагрузки:
#   arecord -l   → должна быть карта googlevoicehat
#   aplay -l     → та же карта

cat > /etc/asound.conf << 'EOF'
# Oiynup ALSA config: googlevoicehat (INMP441 вход + MAX98357 выход)

# Устройство воспроизведения по умолчанию
pcm.!default {
    type asym
    playback.pcm "playback"
    capture.pcm  "capture"
}

pcm.playback {
    type plug
    slave {
        pcm "hw:0,0"
        rate 22050
        channels 2
    }
}

pcm.capture {
    type plug
    slave {
        pcm "hw:0,0"
        rate 16000
        channels 2
        format S32_LE
    }
}

ctl.!default {
    type hw
    card 0
}
EOF

echo "ALSA настроена (/etc/asound.conf)"

# ---------------------------------------------------------------------------
# 6. Права пользователя
# ---------------------------------------------------------------------------
usermod -aG gpio,spi,i2c,audio,video,dialout "$SUDO_USER"
echo "Пользователь $SUDO_USER добавлен в группы: gpio audio video dialout"

# ---------------------------------------------------------------------------
# 7. systemd сервис
# ---------------------------------------------------------------------------
INSTALL_DIR="/home/$SUDO_USER/oiynup"

cat > /etc/systemd/system/oiynup.service << EOF
[Unit]
Description=Oiynup Children Device
After=network.target sound.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR/src
ExecStart=/usr/bin/python3 $INSTALL_DIR/src/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "systemd сервис создан"
echo "  Включить автозапуск: sudo systemctl enable oiynup"

# ---------------------------------------------------------------------------
echo ""
echo "========================================="
echo " Готово! Перезагрузите Pi:"
echo "   sudo reboot"
echo "========================================="
echo ""
echo "После перезагрузки — проверочные команды:"
echo ""
echo "  Звуковые карты:   aplay -l && arecord -l"
echo "  UART:             ls -la /dev/ttyS0"
echo "  Запись микрофона: arecord -D hw:0,0 -c2 -r16000 -f S32_LE -d5 test.wav"
echo "  Прослушать:       aplay test.wav"
echo "  Камера:           libcamera-hello --timeout 3000"
echo ""
echo "  Тест железа:      sudo python3 scripts/test_hardware.py --all"
