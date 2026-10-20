"""
Oiynup — тест железа.

Запуск (нужен root для GPIO/PWM):
  sudo python3 test_hardware.py --all
  sudo python3 test_hardware.py --mic
  sudo python3 test_hardware.py --speaker
  sudo python3 test_hardware.py --led
  sudo python3 test_hardware.py --gsm
  sudo python3 test_hardware.py --camera
  sudo python3 test_hardware.py --list-audio   ← найти номер ALSA устройства
"""

import argparse
import os
import struct
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
from config import config


# ---------------------------------------------------------------------------
# Список аудио устройств
# ---------------------------------------------------------------------------

def list_audio_devices():
    """Показать все ALSA устройства — найти нужный индекс."""
    print("\n--- Доступные аудио устройства ---")
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        count = pa.get_device_count()
        print(f"  Найдено устройств: {count}\n")
        for i in range(count):
            info = pa.get_device_info_by_index(i)
            print(f"  [{i}] {info['name']}")
            print(f"       Вход: {info['maxInputChannels']} кан. | "
                  f"Выход: {info['maxOutputChannels']} кан. | "
                  f"Rate: {int(info['defaultSampleRate'])}Hz")
        pa.terminate()
        print()
        print("  → Найди устройство с 'googlevoicehat' или 'bcm2835'")
        print("  → Поставь его индекс в config.py:")
        print("      config.audio_input.device_index  = <индекс с maxInputChannels>")
        print("      config.audio_output.device_index = <индекс с maxOutputChannels>")
    except ImportError:
        print("  pyaudio не установлена")
    except Exception as exc:
        print(f"  Ошибка: {exc}")


# ---------------------------------------------------------------------------
# Тест микрофона INMP441
# ---------------------------------------------------------------------------

def test_mic():
    print("\n--- Тест микрофона INMP441 (I2S, GPIO20) ---")
    from audio_input import AudioInputModule

    phrases = []

    def on_phrase(data: bytes):
        samples = np.frombuffer(data, dtype=np.int16)
        rms = float(np.sqrt(np.mean(samples.astype(np.float32)**2))) / 32768.0
        duration = len(samples) / config.audio_input.sample_rate
        phrases.append(rms)
        print(f"  ✓ Фраза: {duration:.2f}с  RMS={rms:.5f}")

    mic = AudioInputModule(config.audio_input)
    mic.add_phrase_callback(on_phrase)
    mic.start()

    print(f"  Говори в INMP441 несколько раз, 10 секунд...")
    print(f"  Порог VAD: RMS={config.audio_input.silence_threshold}")
    time.sleep(10)
    mic.stop()

    print(f"\n  Результат: {len(phrases)} фраз обнаружено")
    if phrases:
        print(f"  Средний уровень: RMS={sum(phrases)/len(phrases):.5f}")
        print("  Микрофон: ОК ✓")
    else:
        print("  ⚠ Фразы не обнаружены. Проверь:")
        print("    1. arecord -l → есть ли устройство googlevoicehat?")
        print("    2. Запусти: --list-audio → найди правильный device_index")
        print("    3. SD пин INMP441 → GPIO20 (пин 38)?")
        print("    4. L/R пин INMP441 → GND?")
        print("    5. Попробуй вручную:")
        print("       arecord -D hw:0,0 -c2 -r16000 -f S32_LE -d3 /tmp/test.wav")
        print("       aplay /tmp/test.wav")


# ---------------------------------------------------------------------------
# Тест динамика MAX98357
# ---------------------------------------------------------------------------

def test_speaker():
    print("\n--- Тест динамика MAX98357 (I2S, GPIO21) ---")
    from audio_output import AudioOutputModule

    speaker = AudioOutputModule(config.audio_output)
    speaker.start()
    print("  Произносим: 'Привет! Я Ойнап! Всё работает!'")
    speaker.speak("Привет! Я Ойнап! Всё работает!", language="ru", priority=1)
    time.sleep(6)
    speaker.stop()
    print("  Если слышишь голос из динамика → ОК ✓")
    print("  Если тишина:")
    print("    aplay -l → проверь карту googlevoicehat")
    print("    speaker-test -c 1 -r 22050 -t sine")


# ---------------------------------------------------------------------------
# Тест LED матрицы WS2812B
# ---------------------------------------------------------------------------

def test_led():
    print("\n--- Тест LED матрицы WS2812B (GPIO13 PWM1) ---")
    from led_matrix import LedMatrix

    led = LedMatrix(config.led)
    led.start()
    anims = ["happy", "thinking", "correct", "wrong", "rainbow", "listening"]
    for anim in anims:
        print(f"  Анимация: {anim}")
        led.animation(anim, duration_sec=2)
        time.sleep(2.5)
    led.stop()
    print("  LED: ОК ✓")


# ---------------------------------------------------------------------------
# Тест GSM SIM900
# ---------------------------------------------------------------------------

def test_gsm():
    print("\n--- Тест GSM SIM900 (UART GPIO14/15, RST GPIO17) ---")
    from gsm import GsmModule

    gsm = GsmModule(config.gsm)
    gsm.start()
    time.sleep(3)

    signal = gsm.get_signal_strength()
    ready = gsm.is_ready()
    print(f"  Уровень сигнала: {signal}  (норма 10-25, 99=нет сигнала)")
    print(f"  Модуль инициализирован: {ready}")

    if not ready:
        print("  ⚠ SIM900 не отвечает. Проверь:")
        print("    1. Внешний БП 5V/2A подключён к VCC SIM900?")
        print("    2. TX/RX не перепутаны? RPi GPIO14→SIM900 RXD, GPIO15←SIM900 TXD")
        print("    3. Serial console отключён?")
        print("       grep serial /boot/cmdline.txt  — не должно быть console=serial0")
        print("    4. SIM-карта вставлена, PIN-код отключён?")
    else:
        ans = input(f"  Отправить SMS на {config.gsm.parent_phone}? (y/n): ")
        if ans.strip().lower() == "y":
            ok = gsm.send_parent_alert("system_start")
            print(f"  SMS: {'отправлена ОК ✓' if ok else 'ОШИБКА'}")

    gsm.stop()


# ---------------------------------------------------------------------------
# Тест камеры
# ---------------------------------------------------------------------------

def test_camera():
    print("\n--- Тест камеры (CSI разъём) ---")
    from camera import CameraModule

    cam = CameraModule(config.camera)
    cam.start()
    time.sleep(2)

    frame = cam.capture_frame()
    if frame is not None:
        print(f"  Кадр: {frame.shape}  среднее={frame.mean():.1f}")
        jpeg = cam.capture_jpeg()
        if jpeg:
            path = "/tmp/oiynup_cam_test.jpg"
            with open(path, "wb") as f:
                f.write(jpeg)
            print(f"  JPEG сохранён: {path} ({len(jpeg)} байт)")
        print("  Камера: ОК ✓")
    else:
        print("  ⚠ Кадр не получен.")
        print("    raspi-config → Interface Options → Camera → Enable")
        print("    или: libcamera-hello --timeout 3000")

    cam.stop()


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Oiynup — тест железа")
    parser.add_argument("--all",        action="store_true", help="Все тесты")
    parser.add_argument("--list-audio", action="store_true", help="Список ALSA устройств")
    parser.add_argument("--mic",        action="store_true", help="INMP441 микрофон")
    parser.add_argument("--speaker",    action="store_true", help="MAX98357 динамик")
    parser.add_argument("--led",        action="store_true", help="WS2812B матрица")
    parser.add_argument("--gsm",        action="store_true", help="SIM900 GSM")
    parser.add_argument("--camera",     action="store_true", help="Camera Module")
    args = parser.parse_args()

    run_all = args.all or not any([
        args.list_audio, args.mic, args.speaker, args.led, args.gsm, args.camera
    ])

    try:
        if args.list_audio:               list_audio_devices()
        if run_all or args.led:           test_led()
        if run_all or args.speaker:       test_speaker()
        if run_all or args.mic:           test_mic()
        if run_all or args.gsm:           test_gsm()
        if run_all or args.camera:        test_camera()
    except KeyboardInterrupt:
        print("\n\nПрервано (Ctrl+C)")

    print("\n=== Тесты завершены ===")


if __name__ == "__main__":
    main()
