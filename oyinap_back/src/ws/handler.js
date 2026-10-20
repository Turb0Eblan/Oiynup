const logger = require('../utils/logger');
const { cmdDisplay, cmdSpeak, cmdIdle } = require('./protocol');

/**
 * Обрабатывает входящие сообщения от устройства Oiynup (RPi).
 * Возвращает массив строк — команды для отправки обратно на устройство.
 *
 * @param {object} msg  Распарсенный JSON из WebSocket
 * @param {object} deviceState  Изменяемый объект состояния устройства
 * @returns {string[]}  Список команд для отправки устройству
 */
function handleMessage(msg, deviceState) {
  const type = msg.type;
  const responses = [];

  switch (type) {
    case 'audio': {
      const meta = msg.meta || {};
      logger.debug('Аудио получено', {
        sample_rate: meta.sample_rate,
        format: meta.format,
        bytes: msg.data ? Buffer.byteLength(msg.data, 'base64') : 0,
      });

      // TODO: здесь подключить Whisper / Vosk для распознавания речи
      // TODO: затем передать текст в LLM (Claude API и т.д.)
      // TODO: синтезировать ответ через TTS и вернуть cmdSpeak(text)

      // Заглушка: просто подтверждаем получение анимацией
      responses.push(cmdDisplay('listening', [0, 150, 255], 1.0));
      break;
    }

    case 'video': {
      const meta = msg.meta || {};
      logger.debug('Видеокадр получен', {
        resolution: meta.resolution,
        format: meta.format,
        bytes: msg.data ? Buffer.byteLength(msg.data, 'base64') : 0,
      });

      // TODO: анализ кадра — YOLO, face detection и т.д.
      break;
    }

    case 'status': {
      const meta = msg.meta || {};
      deviceState.uptime = meta.uptime_sec;
      deviceState.wifiIp = meta.wifi_ip;
      deviceState.lastSeen = Date.now();
      logger.info('Статус устройства', { uptime: meta.uptime_sec, ip: meta.wifi_ip });
      break;
    }

    case 'event': {
      const event = (msg.meta || {}).event;
      logger.info(`Событие от устройства: ${event}`);

      if (event === 'system_start') {
        responses.push(cmdDisplay('rainbow', [0, 255, 100], 3.0));
        responses.push(cmdSpeak('Сәлем! Мен сенің досың Ойнап!'));
      } else if (event === 'system_stop') {
        responses.push(cmdDisplay('idle', [50, 50, 50], 1.0));
      }
      break;
    }

    default:
      logger.debug(`Неизвестный тип сообщения: ${type}`);
  }

  return responses;
}

module.exports = { handleMessage };
