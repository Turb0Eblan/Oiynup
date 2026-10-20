const express = require('express');
const path = require('path');
const logger = require('../utils/logger');
const { cmdSpeak, cmdDisplay, cmdSms } = require('../ws/protocol');

function createApiServer({ sendToAll, pipeline }, port) {
  const app = express();
  app.use(express.json());

  // ── Плеер и HLS ─────────────────────────────────────────────────────────

  // HTML-плеер: http://localhost:3000/
  app.get('/', (_req, res) => {
    res.sendFile(path.join(__dirname, '../web/player.html'));
  });

  // HLS сегменты: http://localhost:3000/hls/index.m3u8
  // Подключаем только если ffmpeg пишет в HLS
  if (pipeline && pipeline.hlsDir) {
    app.use('/hls', express.static(pipeline.hlsDir, {
      setHeaders(res) {
        res.set('Cache-Control', 'no-cache');
        res.set('Access-Control-Allow-Origin', '*');
      },
    }));
    logger.info(`HLS плеер: http://localhost:${port}/   сегменты из ${pipeline.hlsDir}`);
  }

  // ── Статус ───────────────────────────────────────────────────────────────

  app.get('/status', (_req, res) => {
    res.json({
      status: 'ok',
      ffmpegReady: pipeline ? pipeline.isReady : false,
      timestamp: new Date().toISOString(),
    });
  });

  // ── Команды на устройство ─────────────────────────────────────────────────

  app.post('/speak', (req, res) => {
    const { text } = req.body;
    if (!text) return res.status(400).json({ error: 'text обязателен' });
    const sent = sendToAll(cmdSpeak(text));
    logger.info(`/speak → ${sent} устройств: "${text}"`);
    res.json({ sent });
  });

  app.post('/display', (req, res) => {
    const { animation = 'idle', color = [0, 100, 255], duration_sec = 2 } = req.body;
    const sent = sendToAll(cmdDisplay(animation, color, duration_sec));
    res.json({ sent });
  });

  app.post('/sms', (req, res) => {
    const { text, phone } = req.body;
    if (!text) return res.status(400).json({ error: 'text обязателен' });
    const sent = sendToAll(cmdSms(text, phone || null));
    logger.info(`/sms → ${sent} устройств: "${text}" → ${phone || 'default'}`);
    res.json({ sent, phone: phone || 'из конфига' });
  });

  app.listen(port, () => logger.info(`REST API + плеер: http://localhost:${port}/`));
  return app;
}

module.exports = { createApiServer };
