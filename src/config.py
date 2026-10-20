"""
Oiynup Device — центральная конфигурация.
"""

from dataclasses import dataclass, field


@dataclass
class CameraConfig:
    resolution: tuple[int, int] = (1280, 720)
    framerate: int = 24
    rotation: int = 0
    capture_interval_sec: float = 0.2


@dataclass
class AudioInputConfig:
    """
    INMP441 — цифровой I2S микрофон.
    ALSA plug конвертирует форматы автоматически через default device.

    Подключение:
      SCK → GPIO18 (пин 12)
      WS  → GPIO19 (пин 35)
      SD  → GPIO20 (пин 38)
      L/R → GND
      VDD → 3.3V
    """
    device_index: int = 0
    sample_rate: int = 16000
    channels: int = 2
    chunk_size: int = 4096   # больший буфер — меньше щелчков
    silence_threshold: float = 0.01
    silence_duration_sec: float = 1.5
    use_channel: int = 0


@dataclass
class AudioOutputConfig:
    """MAX98357 — I2S усилитель через aplay plughw:0,0."""
    device_index: int = 0
    sample_rate: int = 22050
    channels: int = 1


@dataclass
class GsmConfig:
    port: str = "/dev/ttyAMA0"
    baudrate: int = 9600
    reset_pin: int = 17
    timeout_sec: float = 10.0
    parent_phone: str = ""


@dataclass
class LedMatrixConfig:
    pin: int = 13
    num_pixels: int = 64
    matrix_width: int = 8
    matrix_height: int = 8
    brightness: float = 0.7
    led_order: str = "GRB"


@dataclass
class SystemConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    audio_input: AudioInputConfig = field(default_factory=AudioInputConfig)
    audio_output: AudioOutputConfig = field(default_factory=AudioOutputConfig)
    gsm: GsmConfig = field(default_factory=GsmConfig)
    led: LedMatrixConfig = field(default_factory=LedMatrixConfig)

    data_dir: str = "/tmp/oiynup"
    log_file: str = "/home/oiynup/oiynup.log"
    log_level: str = "INFO"
    language: str = "kk"


config = SystemConfig()
