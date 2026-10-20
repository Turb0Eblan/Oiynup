# 0. Быстрый старт — запуск системы

> Этот документ для ежедневной работы. Если настраиваешь с нуля — смотри `2_SETUP.md`.

---

## Что нужно запустить

| Компонент | Где | Как |
|-----------|-----|-----|
| **Node.js бэкенд** | Mac | `npm start` в `oyinap_back/` |
| **oiynup сервис** | RPi | автозапуск (systemd) |
| **Веб-панель** | Mac | `http://localhost:3000/` |

---

## Шаг 1 — Найти IP-адрес Mac

> IP Mac меняется при смене сети. Нужно проверять перед запуском.

```bash
# Узнать текущий IP Mac
ipconfig getifaddr en0        # WiFi
ipconfig getifaddr en1        # Ethernet (если есть)

# Или посмотреть все интерфейсы
ifconfig | grep "inet " | grep -v 127.0.0.1
```

Запомни IP — он понадобится для обновления сервиса на RPi (Шаг 4).

---

## Шаг 2 — Подключиться к RPi по SSH

```bash
# По WiFi (основной способ)
ssh oiynup@<IP_RPI>
# Пароль: <ПАРОЛЬ>

# Если IP изменился — найти через роутер или:
arp -a | grep oiynup
ping -c 1 oiynup.local

# По USB (если WiFi недоступен)
ssh oiynup@10.55.0.1
```

---

## Шаг 3 — Запустить Node.js бэкенд на Mac

```bash
cd ~/projects/Oiynup/oyinap_back

# Запустить (оставить терминал открытым)
~/.nvm/versions/node/v24.14.1/bin/node src/index.js

# Проверить что бэкенд работает:
curl http://localhost:3000/status
# → {"status":"ok","ffmpegReady":true,...}
```

> Если бэкенд уже запущен, пропусти этот шаг.
> Проверить: `ps aux | grep "node.*index" | grep -v grep`

---

## Шаг 4 — Обновить IP Mac в сервисе RPi (если IP изменился)

```bash
# Проверить текущий IP в сервисе
ssh oiynup@<IP_RPI> "grep ExecStart /etc/systemd/system/oiynup.service"

# Если IP отличается от текущего — обновить:
ssh oiynup@<IP_RPI> "echo <ПАРОЛЬ> | sudo -S sed -i 's/--dual-ws .*/--dual-ws <НОВЫЙ_IP>/' /etc/systemd/system/oiynup.service && sudo -S systemctl daemon-reload"

# Пример (IP = <IP_MAC>):
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S sed -i 's/--dual-ws [0-9.]*/--dual-ws <IP_MAC>/' /etc/systemd/system/oiynup.service && sudo -S systemctl daemon-reload"
```

---

## Шаг 5 — Запустить/перезапустить сервис на RPi

```bash
# Проверить статус
ssh oiynup@<IP_RPI> "systemctl is-active oiynup"

# Запустить (если не запущен)
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S systemctl start oiynup"

# Перезапустить (после обновления кода или IP)
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S systemctl restart oiynup"

# Посмотреть логи
ssh oiynup@<IP_RPI> "tail -20 /home/oiynup/oiynup.log"
```

---

## Шаг 6 — Открыть веб-панель

```bash
open http://localhost:3000/
```

В браузере будет:
- **Аудио** — нажми «Слушать» для прослушивания микрофона RPi в реальном времени
- **Видео** — HLS поток с камеры (задержка ~3–6 сек)
- **GSM** — отправить SMS (формат номера: `+77...`)
- **Голос** — произнести текст через динамик RPi
- **LED** — запустить анимацию матрицы

---

## Быстрая проверка что всё работает

```bash
# 1. Бэкенд на Mac
curl -s http://localhost:3000/status

# 2. RPi онлайн
ping -c 1 -t 2 <IP_RPI>

# 3. Сервис запущен и подключён
ssh oiynup@<IP_RPI> "tail -5 /home/oiynup/oiynup.log" 2>/dev/null | grep -E "WS подключён|готов"

# 4. Все три команды сразу
curl -s http://localhost:3000/status && \
ping -c 1 -t 2 <IP_RPI> > /dev/null && echo "RPi: OK" && \
ssh oiynup@<IP_RPI> "grep -c 'WS подключён' /home/oiynup/oiynup.log" 2>/dev/null | xargs -I{} echo "WS соединений сегодня: {}"
```

---

## Деплой кода на RPi

```bash
# Синхронизировать src/ на RPi
rsync -avz \
  --exclude=.DS_Store --exclude=__pycache__ \
  --exclude='*.pyc' --exclude=.claude --exclude='*.jpg' \
  -e 'sshpass -p <ПАРОЛЬ> ssh -o StrictHostKeyChecking=no' \
  ~/projects/Oiynup/src/ \
  oiynup@<IP_RPI>:~/projects/Oiynup/src/

# Перезапустить сервис после деплоя
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S systemctl restart oiynup"
```

---

## Тест железа

```bash
# Остановить сервис (освободить аудио и UART)
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S systemctl stop oiynup"

# Запустить тест (все модули)
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S bash -c 'cd /home/oiynup/projects/Oiynup && python3 scripts/test_hardware.py --all'"

# Отдельные тесты:
# --list-audio    список аудио устройств
# --mic           микрофон INMP441 (10 сек)
# --speaker       динамик MAX98357
# --camera        камера OV5647
# --gsm           GSM SIM900A (спросит отправить ли SMS)
# --led           LED матрица WS2812B (все анимации)

# Не забудь снова запустить сервис после теста:
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S systemctl start oiynup"
```

---

## Остановка системы

```bash
# Остановить сервис на RPi
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S systemctl stop oiynup"

# Остановить Node.js бэкенд на Mac
pkill -f "node.*index.js"

# Выключить RPi
ssh oiynup@<IP_RPI> "printf '<ПАРОЛЬ>\n' | sudo -S shutdown -h now"
```

---

## Важные замечания

### UART и GPIO
> При отладке **никогда не вызывай** `GPIO.setup(14, ...)` или `GPIO.setup(15, ...)` —  
> это сломает UART (TX/RX) и GSM перестанет работать до перезагрузки RPi.

### SIM900A — подключение
> GSM модуль подключён к **TTL порту** (пины T/R/GND на плате, не RS232!).  
> При замене проводов: RPi GPIO14(TX)→R, RPi GPIO15(RX)←T.

### LED матрица WS2812B
> Требует уровень сигнала 3.5V, GPIO13 даёт 3.3V.  
> Если матрица не светится — нужен level shifter (NPN транзистор BC547 или чип 74AHCT125).

### IP адресация
| Устройство | IP | Пользователь | Пароль |
|-----------|-----|-------------|--------|
| RPi Oiynup | <IP_RPI> | oiynup | <ПАРОЛЬ> |
| Mac (бэкенд) | <IP_MAC> | — | — |

> IP Mac может меняться! Проверяй перед запуском (Шаг 1).

---

## Звуки во время работы

| Звук | Где | Причина |
|------|-----|---------|
| **Ping** (высокий тон) | Mac | RPi переподключился к бэкенду |
| **Бип 880Hz** | RPi (динамик) | WebSocket переподключился после разрыва |
| **"Сәлем! Мен сенің досың Ойнап!"** | RPi (динамик) | Приветствие при каждом старте системы |
