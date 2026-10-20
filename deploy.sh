#!/bin/bash
# Oiynup — деплой кода на RPi
# Использование: ./deploy.sh
# Требует: sshpass (brew install sshpass)

RPi_USER="oiynup"
RPi_PASS="${RPI_PASS:-}"
RPi_WIFI="${RPI_WIFI:-}"          # WiFi IP (основной)
RPi_USB="10.55.0.1"          # USB OTG IP (запасной)
RPi_IPV6="${RPI_IPV6:-}"  # IPv6 USB (последний вариант)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=6"

echo "=== Oiynup Deploy ==="

# Определяем как подключиться: WiFi → USB IPv4 → USB IPv6
if ping -c 1 -t 3 "$RPi_WIFI" > /dev/null 2>&1; then
  RPi_HOST="$RPi_WIFI"
  SSH_IPV6=false
  echo "Подключение: WiFi ($RPi_WIFI)"
elif ping -c 1 -t 2 "$RPi_USB" > /dev/null 2>&1; then
  RPi_HOST="$RPi_USB"
  SSH_IPV6=false
  echo "Подключение: USB ($RPi_USB)"
else
  RPi_HOST="$RPi_IPV6"
  SSH_IPV6=true
  echo "Подключение: USB IPv6 ($RPi_IPV6)"
fi

# Копируем проект через tar + SSH
echo "Копирую файлы..."
cd "$PROJECT_DIR" || exit 1

if $SSH_IPV6; then
  tar -czf - --exclude='.git' --exclude='.DS_Store' --exclude='._*' --exclude='__pycache__' . | \
    sshpass -p "$RPi_PASS" ssh -6 $SSH_OPTS \
      "$RPi_USER@$RPi_HOST" \
      "tar -xzf - -C /home/oiynup/oiynup/ && find /home/oiynup/oiynup -name '._*' -delete"
else
  tar -czf - --exclude='.git' --exclude='.DS_Store' --exclude='._*' --exclude='__pycache__' . | \
    sshpass -p "$RPi_PASS" ssh $SSH_OPTS \
      "$RPi_USER@$RPi_HOST" \
      "tar -xzf - -C /home/oiynup/oiynup/ && find /home/oiynup/oiynup -name '._*' -delete"
fi

if [ $? -eq 0 ]; then
  echo "Файлы скопированы ✓"
else
  echo "Ошибка копирования!"
  exit 1
fi

# Перезапуск сервиса
echo "Перезапускаю сервис..."
if $SSH_IPV6; then
  sshpass -p "$RPi_PASS" ssh -6 $SSH_OPTS "$RPi_USER@$RPi_HOST" \
    "echo '$RPi_PASS' | sudo -S systemctl restart oiynup 2>/dev/null || echo 'Сервис не запущен'"
else
  sshpass -p "$RPi_PASS" ssh $SSH_OPTS "$RPi_USER@$RPi_HOST" \
    "echo '$RPi_PASS' | sudo -S systemctl restart oiynup 2>/dev/null || echo 'Сервис не запущен'"
fi

echo ""
echo "=== Готово! ==="
echo "SSH по WiFi: ssh $RPi_USER@$RPi_WIFI"
echo "SSH по USB:  ssh $RPi_USER@$RPi_USB"
echo "Логи:        ssh $RPi_USER@$RPi_WIFI 'journalctl -f -u oiynup'"
