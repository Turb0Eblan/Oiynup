require('dotenv').config();
const logger = require('./utils/logger');
const { FfmpegPipeline } = require('./ffmpeg/pipeline');
const { createAudioServer } = require('./ws/audioServer');
const { createVideoServer } = require('./ws/videoServer');
const { AudioMonitor } = require('./ws/audioMonitor');
const { createApiServer } = require('./api/routes');

const AUDIO_PORT    = parseInt(process.env.AUDIO_PORT    || '8765', 10);
const VIDEO_PORT    = parseInt(process.env.VIDEO_PORT    || '8766', 10);
const MONITOR_PORT  = parseInt(process.env.MONITOR_PORT  || '8767', 10);
const API_PORT      = parseInt(process.env.API_PORT      || '3000', 10);
const FFMPEG_OUTPUT = process.env.FFMPEG_OUTPUT          || '/tmp/oyinap_hls/index.m3u8';

function main() {
  logger.info('=== Oyinap Backend запускается ===');
  logger.info(`Аудио WS : ${AUDIO_PORT} | Видео WS : ${VIDEO_PORT} | Монитор : ${MONITOR_PORT} | API : ${API_PORT}`);
  logger.info(`ffmpeg → ${FFMPEG_OUTPUT}`);

  // ── ffmpeg pipeline (HLS / RTMP / файл) ─────────────────────────────────
  const pipeline = new FfmpegPipeline({
    outputUrl: FFMPEG_OUTPUT,
    audioSampleRate: parseInt(process.env.AUDIO_SAMPLE_RATE || '16000', 10),
    videoFramerate:  parseInt(process.env.VIDEO_FRAMERATE   || '24',    10),
  });
  pipeline.start();

  // ── Прямой аудио монитор для браузера (Web Audio API, без ffmpeg) ────────
  const monitor = new AudioMonitor(MONITOR_PORT);

  // ── WebSocket серверы ────────────────────────────────────────────────────
  const audioCtx = createAudioServer(AUDIO_PORT, pipeline, monitor);
  const videoCtx = createVideoServer(VIDEO_PORT, pipeline);

  // ── REST API + браузерный плеер ──────────────────────────────────────────
  createApiServer({ sendToAll: audioCtx.sendToAll, pipeline }, API_PORT);

  // ── Graceful shutdown ────────────────────────────────────────────────────
  function shutdown(signal) {
    logger.info(`Получен ${signal} — завершение...`);
    pipeline.stop();
    audioCtx.wss.close();
    videoCtx.wss.close();
    process.exit(0);
  }

  process.on('SIGINT',  () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('uncaughtException',  (err)    => logger.error('Необработанное исключение:', err));
  process.on('unhandledRejection', (reason) => logger.error('Необработанный промис:', reason));
}

main();
