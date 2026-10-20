const { WebSocketServer } = require('ws');
const logger = require('../utils/logger');
const { playReconnectSound } = require('../utils/sound');
const { parseMessage, cmdPing } = require('./protocol');
const { handleMessage } = require('./handler');

// Хранилище подключённых устройств: deviceId → { ws, state, pingTimer }
const devices = new Map();

function createWsServer(port) {
  const wss = new WebSocketServer({ port });

  wss.on('listening', () => {
    logger.info(`WebSocket сервер запущен на порту ${port}`);
  });

  wss.on('connection', (ws, req) => {
    const remoteIp = req.socket.remoteAddress;
    const deviceId = remoteIp; // идентификатор по IP; можно расширить на handshake

    const isReconnect = devices.has(deviceId);
    logger.info(`Устройство ${isReconnect ? 'переподключилось' : 'подключилось'}: ${deviceId}`);

    if (isReconnect) {
      // Очищаем старый pingTimer если был
      const prev = devices.get(deviceId);
      if (prev.pingTimer) clearInterval(prev.pingTimer);
      playReconnectSound();
    }

    const deviceState = { ip: remoteIp, connectedAt: Date.now(), lastSeen: Date.now(), uptime: null, wifiIp: null };
    const pingTimer = setInterval(() => {
      if (ws.readyState === ws.OPEN) {
        ws.send(cmdPing());
      }
    }, 30_000);

    devices.set(deviceId, { ws, state: deviceState, pingTimer });

    ws.on('message', (raw) => {
      const msg = parseMessage(raw.toString());
      if (!msg) {
        logger.warn(`Некорректный JSON от ${deviceId}`);
        return;
      }

      // Обновляем lastSeen при любом сообщении
      deviceState.lastSeen = Date.now();

      const responses = handleMessage(msg, deviceState);
      for (const cmd of responses) {
        if (ws.readyState === ws.OPEN) {
          ws.send(cmd);
        }
      }
    });

    ws.on('close', (code, reason) => {
      logger.warn(`Устройство ${deviceId} отключилось (code=${code}, reason=${reason.toString() || 'нет'})`);
      clearInterval(pingTimer);
      // Не удаляем из Map — чтобы следующее подключение определить как reconnect
    });

    ws.on('error', (err) => {
      logger.error(`WebSocket ошибка от ${deviceId}: ${err.message}`);
    });
  });

  wss.on('error', (err) => {
    logger.error(`WebSocket сервер: ${err.message}`);
  });

  return { wss, devices };
}

module.exports = { createWsServer };
