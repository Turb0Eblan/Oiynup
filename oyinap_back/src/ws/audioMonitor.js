/**
 * AudioMonitor — рассылает сырой PCM браузерным клиентам.
 * Браузер декодирует через Web Audio API (нулевая задержка, без ffmpeg).
 */

const { WebSocketServer } = require('ws');
const logger = require('../utils/logger');

class AudioMonitor {
  constructor(port) {
    this._clients = new Set();

    const wss = new WebSocketServer({ port });
    wss.on('listening', () => logger.info(`Аудио монитор: ws://localhost:${port}`));
    wss.on('connection', (ws, req) => {
      const ip = req.socket.remoteAddress;
      logger.info(`Монитор: браузер подключился (${ip})`);
      this._clients.add(ws);
      ws.on('close', () => { this._clients.delete(ws); logger.debug('Монитор: браузер отключился'); });
      ws.on('error', () => this._clients.delete(ws));
    });
  }

  /** Отправить PCM-буфер всем подключённым браузерам. */
  broadcast(pcmBuffer) {
    if (this._clients.size === 0) return;
    for (const ws of this._clients) {
      if (ws.readyState === ws.OPEN) {
        try { ws.send(pcmBuffer); } catch {}
      }
    }
  }
}

module.exports = { AudioMonitor };
