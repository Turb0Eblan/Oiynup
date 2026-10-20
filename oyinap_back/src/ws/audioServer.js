/**
 * AudioServer — WebSocket сервер для аудио (PCM) потока с RPi.
 *
 * Протокол:
 *   binary frames → сырой PCM s16le, записывается прямо в ffmpeg stdin
 *   text frames   → JSON (статус, события) — используется для обратных команд
 *
 * Обратные команды (speak, display, sms...) отправляются по этому же соединению.
 */

const { WebSocketServer } = require('ws');
const logger = require('../utils/logger');
const { playReconnectSound } = require('../utils/sound');
const { cmdDisplay, cmdSpeak, parseMessage } = require('./protocol');

function createAudioServer(port, pipeline, monitor = null) {
  const wss = new WebSocketServer({ port });
  // deviceId → ws  (последнее соединение с этого IP)
  const clients = new Map();
  const connCounts = new Map(); // ip → count

  wss.on('listening', () => logger.info(`Аудио WS сервер: порт ${port}`));

  wss.on('connection', (ws, req) => {
    const ip = req.socket.remoteAddress || 'unknown';
    const prev = connCounts.get(ip) || 0;
    connCounts.set(ip, prev + 1);
    const isReconnect = prev > 0;

    logger.info(`Аудио: ${isReconnect ? 'реконнект' : 'подключение'} ${ip}`);
    if (isReconnect) playReconnectSound();

    clients.set(ip, ws);

    ws.on('message', (data, isBinary) => {
      if (isBinary) {
        // Логируем первые пакеты чтобы убедиться что данные идут
        if (!ws._audioChunkCount) ws._audioChunkCount = 0;
        ws._audioChunkCount++;
        if (ws._audioChunkCount <= 3 || ws._audioChunkCount % 200 === 0) {
          logger.info(`Аудио чанк #${ws._audioChunkCount} от ${ip}: ${data.length} байт`);
        }
        pipeline.writeAudio(data);
        if (monitor) monitor.broadcast(data); // → браузер (Web Audio API)
        return;
      }

      // JSON-сообщение (статус, событие system_start/stop и т.д.)
      const msg = parseMessage(data.toString());
      if (!msg) return;

      if (msg.type === 'event') {
        const event = (msg.meta || {}).event;
        logger.info(`Событие от устройства ${ip}: ${event}`);
        if (event === 'system_start') {
          _safeSend(ws, cmdDisplay('rainbow', [0, 255, 100], 3));
          _safeSend(ws, cmdSpeak('Сәлем! Мен сенің досың Ойнап!'));
        }
      } else if (msg.type === 'status') {
        const m = msg.meta || {};
        logger.info(`Статус ${ip}: uptime=${m.uptime_sec}s ip=${m.wifi_ip}`);
      }
    });

    ws.on('close', (code) => {
      logger.warn(`Аудио: отключение ${ip} (code=${code})`);
      if (clients.get(ip) === ws) clients.delete(ip);
    });

    ws.on('error', (err) => logger.error(`Аудио WS ошибка ${ip}: ${err.message}`));
  });

  wss.on('error', (err) => logger.error(`Аудио WS сервер ошибка: ${err.message}`));

  function sendToAll(cmd) {
    let n = 0;
    for (const ws of clients.values()) {
      if (ws.readyState === ws.OPEN) { ws.send(cmd); n++; }
    }
    return n;
  }

  return { wss, clients, sendToAll };
}

function _safeSend(ws, msg) {
  try { if (ws.readyState === ws.OPEN) ws.send(msg); } catch {}
}

module.exports = { createAudioServer };
