/**
 * VideoServer — WebSocket сервер для видео (MJPEG) потока с RPi.
 *
 * Протокол:
 *   binary frames → сырой JPEG (один кадр = одно сообщение)
 *                   записывается в video pipe → ffmpeg
 *
 * Соединение send-only: сервер ничего не отправляет обратно.
 */

const { WebSocketServer } = require('ws');
const logger = require('../utils/logger');
const { playReconnectSound } = require('../utils/sound');

function createVideoServer(port, pipeline) {
  const wss = new WebSocketServer({ port });
  const clients = new Map();
  const connCounts = new Map();

  let framesTotal = 0;
  let framesDropped = 0;

  wss.on('listening', () => logger.info(`Видео WS сервер: порт ${port}`));

  wss.on('connection', (ws, req) => {
    const ip = req.socket.remoteAddress || 'unknown';
    const prev = connCounts.get(ip) || 0;
    connCounts.set(ip, prev + 1);
    const isReconnect = prev > 0;

    logger.info(`Видео: ${isReconnect ? 'реконнект' : 'подключение'} ${ip}`);
    if (isReconnect) playReconnectSound();

    clients.set(ip, ws);

    ws.on('message', (data, isBinary) => {
      if (!isBinary) return; // игнорируем текст
      framesTotal++;
      const ok = pipeline.writeVideo(data);
      if (!ok) framesDropped++;

      // Логируем статистику каждые 300 кадров
      if (framesTotal % 300 === 0) {
        logger.debug(`Видео: кадры total=${framesTotal} dropped=${framesDropped}`);
      }
    });

    ws.on('close', (code) => {
      logger.warn(`Видео: отключение ${ip} (code=${code})`);
      if (clients.get(ip) === ws) clients.delete(ip);
    });

    ws.on('error', (err) => logger.error(`Видео WS ошибка ${ip}: ${err.message}`));
  });

  wss.on('error', (err) => logger.error(`Видео WS сервер ошибка: ${err.message}`));

  return { wss, clients };
}

module.exports = { createVideoServer };
