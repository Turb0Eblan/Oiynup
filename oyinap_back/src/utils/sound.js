const { execSync } = require('child_process');
const logger = require('./logger');

// Генерируем WAV-файл с двумя короткими бипами в памяти и играем через системные средства
function playReconnectSound() {
  if (process.env.RECONNECT_SOUND !== 'true') return;

  try {
    // Терминальный bell — работает везде без зависимостей
    process.stdout.write('\x07');

    // На Linux дополнительно через paplay/aplay если доступны
    const platform = process.platform;
    if (platform === 'linux') {
      try { execSync('which paplay', { stdio: 'ignore' }); execSync('paplay /usr/share/sounds/freedesktop/stereo/service-login.oga', { stdio: 'ignore', timeout: 2000 }); return; } catch {}
      try { execSync('which aplay', { stdio: 'ignore' }); execSync('aplay /usr/share/sounds/alsa/Front_Center.wav', { stdio: 'ignore', timeout: 2000 }); } catch {}
    } else if (platform === 'darwin') {
      try { execSync('afplay /System/Library/Sounds/Ping.aiff', { stdio: 'ignore', timeout: 2000 }); } catch {}
    }
  } catch (err) {
    logger.debug('Звук реконнекта не воспроизведён:', err.message);
  }
}

module.exports = { playReconnectSound };
