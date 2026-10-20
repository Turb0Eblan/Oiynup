# 1. Железо — компоненты и подключение

## Список компонентов

| # | Компонент | Модель | Кол-во | Примечание |
|---|-----------|--------|--------|-----------|
| 1 | Микрокомпьютер | Raspberry Pi Zero 2 W | 1 | ARM Cortex-A53, WiFi, BT |
| 2 | Камера | Raspberry Pi Camera Module v2 | 1 | 8 Мп, CSI интерфейс |
| 3 | Микрофон | INMP441 | 1 | I2S, 24-бит, до 32kHz |
| 4 | I2S усилитель | MAX98357A | 1 | 3 Вт, класс D |
| 5 | Динамик | Любой 4–8 Ом, до 3 Вт | 1 | |
| 6 | GSM модуль | SIM900 | 1 | UART, 5V/2A |
| 7 | LED матрица | WS2812B 8×8 | 1 | 64 пикселя, 5V |
| 8 | SIM-карта | Любой оператор | 1 | Для SMS |
| 9 | SD карта | 16+ ГБ, Class 10 | 1 | Для RPi OS |
| 10 | Блок питания | 5V / 3A | 1 | Для всей системы |
| 11 | Резистор | 300 Ом | 1 | Защита GPIO13 → LED |
| 12 | Конденсатор | 100 мкФ | 1 | Сглаживание питания LED |

---

## Схема подключения GPIO

```
Raspberry Pi Zero 2 W — 40-pin разъём

       3.3V  [ 1] [ 2] 5V
      GPIO2  [ 3] [ 4] 5V
      GPIO3  [ 5] [ 6] GND  ──→ INMP441 GND, L/R
      GPIO4  [ 7] [ 8] GPIO14 (TXD) ──→ SIM900 RXD
        GND  [ 9] [10] GPIO15 (RXD) ←── SIM900 TXD
     GPIO17  [11] [12] GPIO18 (PCM_CLK) ──→ MAX98357 BCLK
                                          ──→ INMP441 SCK
     GPIO27  [13] [14] GND
     GPIO22  [15] [16] GPIO23
      3.3V   [17] [18] GPIO24
     GPIO10  [19] [20] GND
      GPIO9  [21] [22] GPIO25
     GPIO11  [23] [24] GPIO8
        GND  [25] [26] GPIO7
      GPIO0  [27] [28] GPIO1
      GPIO5  [29] [30] GND
      GPIO6  [31] [32] GPIO12
GPIO13 PWM1  [33] [34] GND
GPIO19 LRCLK [35] [36] GPIO16  ──→ MAX98357 LRC
                                ──→ INMP441 WS
     GPIO26  [37] [38] GPIO20  ←── INMP441 SD
        GND  [39] [40] GPIO21  ──→ MAX98357 DIN
```

---

## Подключение каждого модуля

### 📷 Camera Module v2
```
Лента (15-pin) → CSI разъём RPi
Контакты смотрят К плате. Синяя сторона наружу.
```

### 🎤 INMP441 (I2S микрофон)
| Пин INMP441 | Пин RPi | GPIO |
|-------------|---------|------|
| VDD | 1 | 3.3V |
| GND | 6 | GND |
| L/R | 6 | GND (левый канал) |
| SD  | 38 | GPIO20 (данные → RPi) |
| SCK | 12 | GPIO18 (тактовый) |
| WS  | 35 | GPIO19 (word select) |

> GPIO18 и GPIO19 общие с MAX98357 — подключать параллельно.

### 🔊 MAX98357 (I2S усилитель)
| Пин MAX98357 | Пин RPi | GPIO |
|-------------|---------|------|
| VIN | 1 | 3.3V |
| GND | 39 | GND |
| BCLK | 12 | GPIO18 |
| LRC | 35 | GPIO19 |
| DIN | 40 | GPIO21 (данные ← RPi) |
| SD | — | Не подключать |
| GAIN | GND | — (усиление 9dB) |
| OUT+ | — | → Динамик (+) |
| OUT− | — | → Динамик (−) |

### 📡 SIM900 (GSM/GPRS)
| Пин SIM900 | Откуда |
|------------|--------|
| VCC | ⚠️ Внешний БП 5V/2A (не от RPi!) |
| GND | Общая земля |
| RXD | GPIO14, пин 8 |
| TXD | GPIO15, пин 10 |
| RST | GPIO17, пин 11 |

### 💡 WS2812B (RGB матрица)
| Пин WS2812B | Откуда |
|------------|--------|
| VCC | Внешний БП 5V |
| GND | Общая земля |
| DIN | GPIO13, пин 33 (через резистор 300 Ом) |

---

## Схема питания

```
Блок питания 5V / 3A
│
├── RPi Zero 2 W (через microUSB, разъём PWR)
│   │
│   └── 3.3V (внутренний стабилизатор RPi)
│       ├── INMP441 VDD
│       └── MAX98357 VIN
│
├── SIM900 VCC (до 2A пиков — обязателен отдельный номинал!)
│
└── WS2812B VCC (64 LED × ~60мА = до 3.8A макс, 0.7A при 30%)

Общая шина GND:
  RPi GND ──┬── SIM900 GND
            ├── WS2812B GND
            ├── MAX98357 GND
            └── INMP441 GND
```

---

## Настройки /boot/firmware/config.txt

```ini
[all]
# UART для SIM900
enable_uart=1
dtoverlay=disable-bt

# I2S для INMP441 + MAX98357 (полный дуплекс)
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard

# PWM для WS2812B (GPIO13)
core_freq=500
core_freq_min=500

# USB OTG (SSH без WiFi)
dtoverlay=dwc2
```

Настройки /boot/firmware/cmdline.txt (добавить к rootwait):
```
modules-load=dwc2,g_ether
```
