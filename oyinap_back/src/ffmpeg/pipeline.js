/**
 * FfmpegPipeline
 *
 * Аудио → ffmpeg stdin  (PCM s16le)
 * Видео → named FIFO   (MJPEG: один JPEG = один binary WS message)
 *
 * start() — неблокирующий. ffmpeg запускается в фоне.
 * Если ffmpeg не найден / упал — авто-рестарт каждые 3 сек.
 * writeAudio/writeVideo — no-op если ffmpeg не готов.
 */

const { spawn, execSync } = require('child_process');
const fs = require('fs');
const logger = require('../utils/logger');

const VIDEO_PIPE = '/tmp/oiynup_video.pipe';
const RESTART_MS = 3000;
const PIPE_OPEN_TIMEOUT_MS = 10_000;

class FfmpegPipeline {
  constructor({ outputUrl, audioSampleRate = 16000, videoFramerate = 24 }) {
    this.outputUrl = outputUrl;
    this.audioSampleRate = audioSampleRate;
    this.videoFramerate = videoFramerate;

    this._process = null;
    this._videoPipeWriter = null;
    this._running = false;
    this._ready = false; // ffmpeg поднят и pipe открыт
  }

  // ── Жизненный цикл ────────────────────────────────────────────────────────

  /** Неблокирующий старт — ffmpeg поднимается в фоне. */
  start() {
    this._running = true;
    logger.info(`FfmpegPipeline: цель → ${this.outputUrl}`);
    this._launch(); // async, не await-им
  }

  stop() {
    this._running = false;
    this._ready = false;
    if (this._process) {
      try { this._process.stdin.end(); } catch {}
      try { this._process.kill('SIGTERM'); } catch {}
      this._process = null;
    }
    this._closeVideoPipe();
    try { fs.unlinkSync(VIDEO_PIPE); } catch {}
  }

  // ── Запись данных (no-op когда ffmpeg не готов) ───────────────────────────

  writeAudio(buf) {
    if (!this._ready || !this._process || this._process.killed) return;
    try { this._process.stdin.write(buf); } catch {}
  }

  writeVideo(buf) {
    if (!this._ready || !this._videoPipeWriter || this._videoPipeWriter.destroyed) return false;
    const ok = this._videoPipeWriter.write(buf);
    if (!ok) logger.debug('Video pipe backpressure — кадр пропущен');
    return ok;
  }

  get isReady() { return this._ready; }

  // ── Внутренние методы ─────────────────────────────────────────────────────

  async _launch() {
    if (!this._running) return;

    this._ready = false;
    this._closeVideoPipe();
    this._ensureVideoPipe();

    // Запускаем ffmpeg
    const args = this._buildArgs();
    logger.debug('ffmpeg args:', args.join(' '));

    let proc;
    try {
      proc = spawn('ffmpeg', args, { stdio: ['pipe', 'ignore', 'pipe'] });
    } catch (err) {
      logger.error(`ffmpeg spawn error: ${err.message}`);
      this._scheduleRestart();
      return;
    }

    this._process = proc;
    let spawnFailed = false;

    proc.stderr.on('data', (d) => {
      const line = d.toString().trim();
      if (line) logger.debug(`ffmpeg: ${line}`);
    });

    proc.on('error', (err) => {
      spawnFailed = true;
      logger.error(`ffmpeg не найден/не запустился: ${err.message}`);
    });

    proc.on('close', (code) => {
      this._ready = false;
      this._closeVideoPipe();
      logger.warn(`ffmpeg завершился (code=${code})`);
      if (this._running) this._scheduleRestart();
    });

    // Даём 500 мс чтобы поймать ошибку старта (ENOENT и т.д.)
    await new Promise((r) => setTimeout(r, 500));
    if (spawnFailed || proc.killed) return;

    // Открываем write-конец video FIFO (блокируется пока ffmpeg не откроет read-конец)
    try {
      this._videoPipeWriter = await this._openPipeWriter(VIDEO_PIPE, PIPE_OPEN_TIMEOUT_MS);
      this._ready = true;
      logger.info('ffmpeg готов — аудио+видео принимаются');
    } catch (err) {
      logger.error(`Video pipe не открылся: ${err.message}`);
      try { proc.kill('SIGTERM'); } catch {}
    }
  }

  _scheduleRestart() {
    logger.info(`ffmpeg перезапуск через ${RESTART_MS}ms...`);
    setTimeout(() => this._launch(), RESTART_MS);
  }

  _ensureVideoPipe() {
    try {
      if (fs.existsSync(VIDEO_PIPE)) fs.unlinkSync(VIDEO_PIPE);
      execSync(`mkfifo ${VIDEO_PIPE}`);
    } catch (err) {
      logger.error(`mkfifo: ${err.message}`);
    }
  }

  _closeVideoPipe() {
    if (this._videoPipeWriter) {
      try { this._videoPipeWriter.destroy(); } catch {}
      this._videoPipeWriter = null;
    }
  }

  /** Возвращает путь к HLS-директории если вывод — HLS, иначе null */
  get hlsDir() {
    if (this.outputUrl.endsWith('.m3u8')) {
      return require('path').dirname(this.outputUrl);
    }
    return null;
  }

  _buildArgs() {
    const out = this.outputUrl;
    let fmt, extraOut;
    if (out.startsWith('rtmp://') || out.startsWith('rtmps://')) {
      fmt = 'flv';
      extraOut = [];
    } else if (out.endsWith('.m3u8')) {
      fmt = 'hls';
      extraOut = [
        '-hls_time', '2',
        '-hls_list_size', '5',
        '-hls_flags', 'delete_segments+append_list',
        '-hls_segment_filename', require('path').join(require('path').dirname(out), 'seg%03d.ts'),
      ];
      // Создаём директорию для HLS файлов
      try { fs.mkdirSync(require('path').dirname(out), { recursive: true }); } catch {}
    } else {
      fmt = 'mp4';
      extraOut = ['-movflags', 'frag_keyframe+empty_moov'];
    }

    return [
      '-loglevel', 'warning',
      '-f', 's16le', '-ar', String(this.audioSampleRate), '-ac', '1', '-i', 'pipe:0',
      '-f', 'mjpeg', '-framerate', String(this.videoFramerate), '-i', VIDEO_PIPE,
      '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
      '-g', String(this.videoFramerate * 2),
      '-c:a', 'aac', '-b:a', '64k', '-ar', '44100',
      '-f', fmt, ...extraOut, out,
    ];
  }

  _openPipeWriter(pipePath, timeoutMs) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`Timeout ${timeoutMs}ms открытия ${pipePath}`)),
        timeoutMs,
      );
      fs.open(pipePath, 'w', (err, fd) => {
        clearTimeout(timer);
        if (err) return reject(err);
        const stream = fs.createWriteStream(null, { fd, autoClose: true });
        stream.on('error', (e) => logger.warn(`Video pipe writer: ${e.message}`));
        resolve(stream);
      });
    });
  }
}

module.exports = { FfmpegPipeline };
