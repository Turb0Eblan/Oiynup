#!/usr/bin/env python3
"""
Oiynup Control Panel — веб-панель управления устройством.
Запуск: python3 panel.py
Открывает браузер автоматически на http://localhost:7777
"""

import subprocess, sys

def _install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for pkg in ["flask", "paramiko"]:
    try:
        __import__(pkg)
    except ImportError:
        print(f"Устанавливаю {pkg}..."); _install(pkg)

# ─────────────────────────────────────────────────────────────────────────────
from flask import Flask, render_template_string, request, jsonify, Response
import paramiko, threading, socket, json, base64, io, time, os, subprocess
from pathlib import Path
from datetime import datetime
from queue import Queue, Empty

app = Flask(__name__)
PROJECT_DIR = Path(__file__).parent
CONFIG_FILE = PROJECT_DIR / ".panel_config.json"

DEFAULTS = {
    "host":         "",
    "user":         "oiynup",
    "password":     "",
    "parent_phone": "+7XXXXXXXXXX",
    "rpi_path":     "/home/oiynup/oiynup",
}

# ── Состояние ─────────────────────────────────────────────────────────────────
ssh_client  = None
ssh_lock    = threading.Lock()
log_queue   = Queue(maxsize=500)
cfg         = {**DEFAULTS, **(json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {})}


def save_cfg():
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── SSH helpers ───────────────────────────────────────────────────────────────

def ssh_connect(host, user, password):
    global ssh_client
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_host = host.split('%')[0] if '%' in host else host
    if '%' in host:
        zone = host.split('%')[1]
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((connect_host, 22, 0, socket.if_nametoindex(zone)))
        client.connect(connect_host, username=user, password=password,
                       timeout=15, sock=sock, allow_agent=False, look_for_keys=False)
    else:
        client.connect(host, username=user, password=password,
                       timeout=15, allow_agent=False, look_for_keys=False)
    with ssh_lock:
        ssh_client = client
    return True


def ssh_run(cmd, timeout=30):
    with ssh_lock:
        c = ssh_client
    if not c:
        return "", "Нет подключения"
    try:
        _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
        return stdout.read().decode('utf-8', errors='replace'), \
               stderr.read().decode('utf-8', errors='replace')
    except Exception as e:
        return "", str(e)


def ssh_sudo(cmd, timeout=60):
    return ssh_run(f"echo '{cfg['password']}' | sudo -S {cmd}", timeout=timeout)


def is_connected():
    with ssh_lock:
        c = ssh_client
    if not c:
        return False
    try:
        t = c.get_transport()
        return t is not None and t.is_active()
    except Exception:
        return False


def push_log(msg, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    try:
        log_queue.put_nowait({"ts": ts, "msg": msg, "level": level})
    except Exception:
        pass


# ── HTML шаблон ───────────────────────────────────────────────────────────────

HTML = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oiynup Control Panel</title>
<style>
  :root {
    --bg:    #0f1117; --panel: #1a1d2e; --border: #2d3148;
    --accent:#7c3aed; --green: #22c55e; --red:   #ef4444;
    --yellow:#eab308; --text:  #e2e8f0; --muted: #64748b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: var(--bg); color: var(--text); min-height: 100vh; }

  header { background: var(--accent); padding: 14px 24px;
           display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 1.3rem; font-weight: 700; }
  #conn-badge { font-size:.85rem; padding:4px 12px; border-radius:20px;
                background:rgba(0,0,0,.3); }

  nav { display: flex; background: var(--panel); border-bottom: 1px solid var(--border); }
  nav button { background: none; border: none; color: var(--muted); padding: 12px 20px;
               cursor: pointer; font-size: .95rem; border-bottom: 3px solid transparent; }
  nav button.active, nav button:hover { color: var(--text); }
  nav button.active { border-color: var(--accent); color: var(--accent); font-weight: 600; }

  .tab { display: none; padding: 24px; max-width: 1000px; margin: 0 auto; }
  .tab.active { display: block; }

  .card { background: var(--panel); border: 1px solid var(--border);
          border-radius: 10px; padding: 20px; margin-bottom: 16px; }
  .card h3 { color: var(--muted); font-size: .8rem; text-transform: uppercase;
             letter-spacing: .08em; margin-bottom: 14px; }

  label { color: var(--muted); font-size: .85rem; display: block; margin-bottom: 4px; }
  input[type=text], input[type=password], textarea {
    width: 100%; background: #0a0c14; border: 1px solid var(--border);
    border-radius: 6px; color: var(--text); padding: 10px 12px;
    font-size: .95rem; outline: none; margin-bottom: 12px; }
  input:focus, textarea:focus { border-color: var(--accent); }

  .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  .row input, .row select { flex: 1; margin-bottom: 0; }

  button.btn { border: none; border-radius: 6px; padding: 9px 18px;
               font-size: .9rem; font-weight: 600; cursor: pointer; color: #fff; }
  .btn-accent { background: var(--accent); }
  .btn-green  { background: var(--green); }
  .btn-red    { background: var(--red); }
  .btn-muted  { background: var(--muted); }
  .btn-yellow { background: var(--yellow); color: #000; }
  .btn:hover  { opacity: .85; }

  .status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .status-item { background: #0a0c14; border-radius: 8px; padding: 12px;
                 text-align: center; }
  .status-item .name { font-size: .8rem; color: var(--muted); margin-bottom: 6px; }
  .status-item .val  { font-size: 1rem; font-weight: 700; }

  .log-box { background: #07090f; border: 1px solid var(--border); border-radius: 8px;
             padding: 12px; height: 320px; overflow-y: auto; font-family: monospace;
             font-size: .82rem; line-height: 1.5; }
  .log-box .info { color: var(--text); }
  .log-box .ok   { color: var(--green); }
  .log-box .err  { color: var(--red); }
  .log-box .warn { color: var(--yellow); }
  .log-box .dim  { color: var(--muted); }

  .progress-wrap { background:#0a0c14; border-radius:6px; height:8px; margin:8px 0; }
  .progress-bar  { height:8px; border-radius:6px; background:var(--green);
                   transition:width .4s; width:0%; }

  #cam-img { max-width:100%; border-radius:8px; display:none;
             border:1px solid var(--border); }
  #cam-placeholder { color:var(--muted); text-align:center; padding:60px 0; }

  .spinner { display:none; width:20px; height:20px; border:3px solid var(--border);
             border-top-color:var(--accent); border-radius:50%;
             animation:spin .7s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }

  @media(max-width:600px) {
    .status-grid { grid-template-columns: 1fr 1fr; }
    nav button { padding: 10px 12px; font-size:.85rem; }
  }
</style>
</head>
<body>

<header>
  <h1>⬡ Oiynup Control Panel</h1>
  <span id="conn-badge">● Отключено</span>
</header>

<nav>
  <button class="active" onclick="showTab('connect',this)">🔗 Подключение</button>
  <button onclick="showTab('deploy',this)">🚀 Деплой</button>
  <button onclick="showTab('camera',this)">📷 Камера</button>
  <button onclick="showTab('audio',this)">🎤 Аудио</button>
  <button onclick="showTab('gsm',this)">📡 GSM</button>
  <button onclick="showTab('logs',this)">📋 Логи</button>
</nav>

<!-- ══════════════ ПОДКЛЮЧЕНИЕ ══════════════ -->
<div id="tab-connect" class="tab active">
  <div class="card">
    <h3>SSH соединение</h3>
    <label>Host / IPv6</label>
    <input id="host" type="text" value="{{ cfg.host }}">
    <label>Пользователь</label>
    <input id="user" type="text" value="{{ cfg.user }}">
    <label>Пароль</label>
    <input id="pass" type="password" value="{{ cfg.password }}">
    <div class="row">
      <button class="btn btn-accent" onclick="connect()">Подключиться</button>
      <button class="btn btn-red"    onclick="disconnect()">Отключиться</button>
      <button class="btn btn-yellow" onclick="autoDiscover()">🔍 Авто-поиск</button>
      <div class="spinner" id="conn-spin"></div>
    </div>
  </div>

  <div class="card">
    <h3>Состояние модулей</h3>
    <div class="status-grid">
      <div class="status-item"><div class="name">WiFi</div>
        <div class="val" id="hw-wlan">—</div></div>
      <div class="status-item"><div class="name">USB OTG</div>
        <div class="val" id="hw-usb">—</div></div>
      <div class="status-item"><div class="name">Камера</div>
        <div class="val" id="hw-cam">—</div></div>
      <div class="status-item"><div class="name">I2S аудио</div>
        <div class="val" id="hw-i2s">—</div></div>
      <div class="status-item"><div class="name">UART/SIM</div>
        <div class="val" id="hw-uart">—</div></div>
      <div class="status-item"><div class="name">Uptime</div>
        <div class="val" id="hw-uptime" style="font-size:.8rem">—</div></div>
    </div>
    <br>
    <button class="btn btn-green" onclick="checkHardware()">🔍 Проверить всё</button>
  </div>
</div>

<!-- ══════════════ ДЕПЛОЙ ══════════════ -->
<div id="tab-deploy" class="tab">
  <div class="card">
    <h3>Загрузка кода на RPi</h3>
    <label>Путь на RPi</label>
    <input id="rpi-path" type="text" value="{{ cfg.rpi_path }}">
    <div class="row" style="margin-bottom:14px">
      <button class="btn btn-accent" onclick="deploy()">⬆ Загрузить код</button>
      <button class="btn btn-green"  onclick="startSystem()">▶ Запустить</button>
      <button class="btn btn-red"    onclick="stopSystem()">⏹ Остановить</button>
      <div class="spinner" id="deploy-spin"></div>
    </div>
    <div class="progress-wrap"><div class="progress-bar" id="deploy-bar"></div></div>
    <div class="log-box" id="deploy-log"></div>
  </div>
</div>

<!-- ══════════════ КАМЕРА ══════════════ -->
<div id="tab-camera" class="tab">
  <div class="card">
    <h3>Camera Module</h3>
    <div class="row" style="margin-bottom:16px">
      <button class="btn btn-accent" onclick="camCapture()">📸 Снять кадр</button>
      <button class="btn btn-green"  onclick="camStream()">▶ Стрим (5 кадров)</button>
      <button class="btn btn-muted"  onclick="camSave()">💾 Сохранить</button>
      <div class="spinner" id="cam-spin"></div>
    </div>
    <div id="cam-placeholder">Нажми «Снять кадр»</div>
    <img id="cam-img" src="" alt="Camera">
  </div>
</div>

<!-- ══════════════ АУДИО ══════════════ -->
<div id="tab-audio" class="tab">
  <div class="card">
    <h3>Микрофон INMP441</h3>
    <div class="row" style="margin-bottom:12px">
      <button class="btn btn-accent" onclick="micRecord()">⏺ Записать (~7 сек)</button>
      <button class="btn btn-green"  onclick="micPlay()">▶ Через динамик</button>
      <div class="spinner" id="mic-spin"></div>
    </div>
    <label>Уровень сигнала: <span id="mic-pct">—</span></label>
    <div class="progress-wrap"><div class="progress-bar" id="mic-bar"></div></div>

    <!-- Плеер прямо в браузере -->
    <div id="mic-player-wrap" style="display:none; margin-top:14px">
      <label style="margin-bottom:6px; display:block">▶ Прослушать в браузере:</label>
      <audio id="mic-player" controls style="width:100%; border-radius:6px;"></audio>
    </div>
  </div>
  <div class="card">
    <h3>Динамик MAX98357</h3>
    <label>Текст для TTS</label>
    <input id="tts-text" type="text" value="Привет! Я Ойнап!">
    <div class="row">
      <button class="btn btn-accent" onclick="speakerSpeak()">🗣 Произнести</button>
      <button class="btn btn-green"  onclick="speakerSine()">🔊 Синус-тест</button>
      <div class="spinner" id="spk-spin"></div>
    </div>
  </div>
</div>

<!-- ══════════════ GSM ══════════════ -->
<div id="tab-gsm" class="tab">
  <div class="card">
    <h3>Уровень сигнала SIM900</h3>
    <div class="row" style="margin-bottom:12px">
      <button class="btn btn-accent" onclick="gsmSignal()">📶 Проверить</button>
      <span id="signal-txt" style="font-size:1.1rem;font-weight:700">—</span>
      <div class="spinner" id="gsm-spin"></div>
    </div>
    <div class="progress-wrap">
      <div class="progress-bar" id="signal-bar" style="background:var(--accent)"></div>
    </div>
  </div>
  <div class="card">
    <h3>Отправить SMS</h3>
    <label>Номер телефона</label>
    <input id="sms-phone" type="text" value="{{ cfg.parent_phone }}">
    <label>Текст сообщения</label>
    <input id="sms-text" type="text" value="Привет от Ойнап!">
    <div class="row">
      <button class="btn btn-accent" onclick="sendSms()">📨 Отправить SMS</button>
      <div class="spinner" id="sms-spin"></div>
      <span id="sms-status"></span>
    </div>
  </div>
</div>

<!-- ══════════════ ЛОГИ ══════════════ -->
<div id="tab-logs" class="tab">
  <div class="card">
    <h3>Системные логи RPi</h3>
    <div class="row" style="margin-bottom:12px">
      <button class="btn btn-accent" onclick="fetchLogs()">📥 Получить логи</button>
      <button class="btn btn-green"  onclick="startLogStream()">⏺ Стрим</button>
      <button class="btn btn-red"    onclick="stopLogStream()">⏹ Стоп</button>
      <button class="btn btn-muted"  onclick="clearLogs()">🗑 Очистить</button>
    </div>
    <div class="log-box" id="main-log"></div>
  </div>
</div>

<script>
let logStreamActive = false;
let logEs = null;
let lastCamData = null;

// ── Вкладки ──────────────────────────────────────────────────────────────────
function showTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}

// ── Логи ─────────────────────────────────────────────────────────────────────
function addLog(box, msg, level) {
  const el = document.getElementById(box);
  const line = document.createElement('div');
  const ts = new Date().toTimeString().slice(0,8);
  line.className = level || 'info';
  line.textContent = `[${ts}] ${msg}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

function clearLogs() { document.getElementById('main-log').innerHTML = ''; }

// ── SSE лог-стрим ─────────────────────────────────────────────────────────────
function startLogStream() {
  if (logEs) logEs.close();
  logEs = new EventSource('/api/log-stream');
  logEs.onmessage = e => {
    const d = JSON.parse(e.data);
    addLog('main-log', d.msg, d.level);
  };
  logStreamActive = true;
}
function stopLogStream() {
  if (logEs) { logEs.close(); logEs = null; }
  logStreamActive = false;
  addLog('main-log', '--- стрим остановлен ---', 'dim');
}

// ── API helper ────────────────────────────────────────────────────────────────
async function api(endpoint, data, spinId) {
  const spin = spinId ? document.getElementById(spinId) : null;
  if (spin) spin.style.display = 'inline-block';
  try {
    const resp = await fetch('/api/' + endpoint, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(data || {})
    });
    return await resp.json();
  } catch(e) {
    return {ok: false, msg: e.toString()};
  } finally {
    if (spin) spin.style.display = 'none';
  }
}

// ── Подключение ───────────────────────────────────────────────────────────────
async function connect() {
  const r = await api('connect', {
    host: document.getElementById('host').value,
    user: document.getElementById('user').value,
    password: document.getElementById('pass').value,
  }, 'conn-spin');
  const badge = document.getElementById('conn-badge');
  if (r.ok) {
    badge.textContent = '● Подключено';
    badge.style.background = 'rgba(34,197,94,.3)';
    addLog('main-log', r.msg, 'ok');
  } else {
    badge.textContent = '● Отключено';
    badge.style.background = 'rgba(239,68,68,.3)';
    addLog('main-log', 'Ошибка: ' + r.msg, 'err');
  }
}

async function disconnect() {
  await api('disconnect');
  document.getElementById('conn-badge').textContent = '● Отключено';
  document.getElementById('conn-badge').style.background = '';
  addLog('main-log', 'Отключено', 'dim');
}

async function autoDiscover() {
  addLog('main-log', 'Ищу RPi...', 'dim');
  const r = await api('discover', {}, 'conn-spin');
  if (r.ok) {
    document.getElementById('host').value = r.host;
    addLog('main-log', 'Найден: ' + r.host, 'ok');
  } else {
    addLog('main-log', r.msg, 'warn');
  }
}

// ── Железо ───────────────────────────────────────────────────────────────────
async function checkHardware() {
  addLog('main-log', 'Проверяю железо...', 'dim');
  const r = await api('hw-check');
  if (!r.ok) { addLog('main-log', r.msg, 'err'); return; }
  const icons = {true: '✓ OK', false: '✗ нет'};
  const colors = {true: 'var(--green)', false: 'var(--red)'};
  for (const [k, v] of Object.entries(r.data)) {
    const el = document.getElementById('hw-' + k);
    if (el) { el.textContent = icons[v]; el.style.color = colors[v]; }
    addLog('main-log', k + ': ' + (v ? 'OK' : 'НЕТ'), v ? 'ok' : 'err');
  }
  if (r.uptime) {
    document.getElementById('hw-uptime').textContent = r.uptime;
  }
}

// ── Деплой ───────────────────────────────────────────────────────────────────
function deployLog(msg) { addLog('deploy-log', msg, 'info'); }

async function deploy() {
  const bar = document.getElementById('deploy-bar');
  bar.style.width = '10%';
  addLog('deploy-log', 'Начинаю деплой...', 'dim');
  const r = await api('deploy', {
    rpi_path: document.getElementById('rpi-path').value
  }, 'deploy-spin');
  bar.style.width = r.ok ? '100%' : '0%';
  addLog('deploy-log', r.msg, r.ok ? 'ok' : 'err');
}

async function startSystem() {
  const r = await api('system-start');
  addLog('deploy-log', r.msg, r.ok ? 'ok' : 'err');
}
async function stopSystem() {
  const r = await api('system-stop');
  addLog('deploy-log', r.msg, r.ok ? 'ok' : 'err');
}

// ── Камера ───────────────────────────────────────────────────────────────────
async function camCapture() {
  const r = await api('cam-capture', {}, 'cam-spin');
  if (r.ok && r.image) {
    lastCamData = r.image;
    document.getElementById('cam-img').src = 'data:image/jpeg;base64,' + r.image;
    document.getElementById('cam-img').style.display = 'block';
    document.getElementById('cam-placeholder').style.display = 'none';
    addLog('main-log', 'Кадр получен', 'ok');
  } else {
    addLog('main-log', 'Ошибка камеры: ' + r.msg, 'err');
  }
}

async function camStream() {
  for (let i = 0; i < 5; i++) {
    await camCapture();
    await new Promise(r => setTimeout(r, 1200));
  }
}

function camSave() {
  if (!lastCamData) { alert('Сначала сними кадр'); return; }
  const a = document.createElement('a');
  a.href = 'data:image/jpeg;base64,' + lastCamData;
  a.download = 'oiynup_' + Date.now() + '.jpg';
  a.click();
}

// ── Аудио ────────────────────────────────────────────────────────────────────
async function micRecord() {
  addLog('main-log', 'Останавливаю сервис и начинаю запись (~7 сек)...', 'dim');
  document.getElementById('mic-player-wrap').style.display = 'none';
  const r = await api('mic-record', {}, 'mic-spin');
  if (r.ok) {
    const pct = r.level || 0;
    document.getElementById('mic-bar').style.width = pct + '%';
    document.getElementById('mic-pct').textContent = pct + '%' + (pct < 5 ? ' ⚠ тихо' : ' ✓');
    document.getElementById('mic-pct').style.color = pct < 5 ? 'var(--red)' : 'var(--green)';
    addLog('main-log', `Микрофон: ${pct}%`, pct < 5 ? 'warn' : 'ok');
    // Загружаем аудио в браузерный плеер
    const player = document.getElementById('mic-player');
    player.src = '/api/mic-audio?' + Date.now();  // cache-bust
    document.getElementById('mic-player-wrap').style.display = 'block';
    player.load();
  } else {
    addLog('main-log', r.msg, 'err');
  }
}
async function micPlay() {
  const r = await api('mic-play');
  addLog('main-log', r.msg, r.ok ? 'ok' : 'err');
}
async function speakerSpeak() {
  const r = await api('speaker-speak', {text: document.getElementById('tts-text').value}, 'spk-spin');
  addLog('main-log', r.msg, r.ok ? 'ok' : 'err');
}
async function speakerSine() {
  const r = await api('speaker-sine', {}, 'spk-spin');
  addLog('main-log', r.msg, r.ok ? 'ok' : 'err');
}

// ── GSM ──────────────────────────────────────────────────────────────────────
async function gsmSignal() {
  const r = await api('gsm-signal', {}, 'gsm-spin');
  if (r.ok) {
    const pct = Math.min(100, (r.signal / 31) * 100);
    document.getElementById('signal-bar').style.width = pct + '%';
    document.getElementById('signal-bar').style.background =
      r.signal > 15 ? 'var(--green)' : r.signal > 5 ? 'var(--yellow)' : 'var(--red)';
    document.getElementById('signal-txt').textContent = r.text;
    document.getElementById('signal-txt').style.color =
      r.signal > 15 ? 'var(--green)' : r.signal > 5 ? 'var(--yellow)' : 'var(--red)';
    addLog('main-log', 'GSM: ' + r.text, r.signal > 5 ? 'ok' : 'warn');
  } else {
    addLog('main-log', r.msg, 'err');
  }
}

async function sendSms() {
  const r = await api('gsm-sms', {
    phone: document.getElementById('sms-phone').value,
    text:  document.getElementById('sms-text').value,
  }, 'sms-spin');
  const s = document.getElementById('sms-status');
  s.textContent = r.msg;
  s.style.color = r.ok ? 'var(--green)' : 'var(--red)';
  addLog('main-log', r.msg, r.ok ? 'ok' : 'err');
}

// ── Логи RPi ─────────────────────────────────────────────────────────────────
async function fetchLogs() {
  addLog('main-log', '--- получаю логи ---', 'dim');
  const r = await api('logs-fetch');
  if (r.ok && r.lines) {
    r.lines.forEach(l => {
      const lvl = l.includes('ERROR') ? 'err' : l.includes('WARN') ? 'warn' : 'info';
      addLog('main-log', l, lvl);
    });
  }
}

// Авто-подключение SSE лог-стрима при загрузке
window.addEventListener('load', () => startLogStream());
</script>
</body>
</html>
"""

# ── API маршруты ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template_string(HTML, cfg=cfg)


@app.route('/api/connect', methods=['POST'])
def api_connect():
    d = request.json
    cfg.update({k: d[k] for k in ('host', 'user', 'password') if k in d})
    save_cfg()
    try:
        ssh_connect(d['host'], d['user'], d['password'])
        out, _ = ssh_run("hostname && uptime -p")
        push_log(f"Подключено: {out.strip()}", "ok")
        return jsonify(ok=True, msg=f"Подключено ✓  {out.strip()}")
    except Exception as e:
        return jsonify(ok=False, msg=str(e))


@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    global ssh_client
    with ssh_lock:
        if ssh_client:
            ssh_client.close()
            ssh_client = None
    return jsonify(ok=True)


@app.route('/api/discover', methods=['POST'])
def api_discover():
    try:
        r = subprocess.run(['dns-sd', '-q', 'oiynup.local', 'AAAA'],
                           capture_output=True, text=True, timeout=6)
        for line in r.stdout.splitlines():
            if 'AAAA' in line and 'FE80' in line.upper():
                ipv6_raw = line.split()[-1].lower()
                # найти интерфейс RPi
                iface_r = subprocess.run(['networksetup', '-listallhardwareports'],
                                         capture_output=True, text=True)
                iface = 'en6'
                lines = iface_r.stdout.splitlines()
                for i, l in enumerate(lines):
                    if 'Raspberry Pi' in l and i + 1 < len(lines):
                        dev = lines[i + 1]
                        if 'Device:' in dev:
                            iface = dev.split(':')[-1].strip()
                host = f"{ipv6_raw}%{iface}"
                return jsonify(ok=True, host=host)
        return jsonify(ok=False, msg='RPi не найден. Проверь USB кабель.')
    except Exception as e:
        return jsonify(ok=False, msg=str(e))


@app.route('/api/hw-check', methods=['POST'])
def api_hw_check():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    checks = {
        'wlan':  "ip link show wlan0 2>/dev/null | grep -c UP",
        'usb':   "ip addr show usb0 2>/dev/null | grep -c '10.55'",
        'cam':   "libcamera-hello --list-cameras 2>&1 | grep -c 'Available'",
        'i2s':   "aplay -l 2>/dev/null | grep -ic 'googlevoicehat\\|hifiberry\\|bcm'",
        'uart':  "ls /dev/ttyS0 2>/dev/null | wc -l",
    }
    data = {}
    for k, cmd in checks.items():
        out, _ = ssh_run(cmd)
        data[k] = out.strip() == '1'
    uptime, _ = ssh_run("uptime -p")
    return jsonify(ok=True, data=data, uptime=uptime.strip())


@app.route('/api/deploy', methods=['POST'])
def api_deploy():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    rpi_path = request.json.get('rpi_path', cfg['rpi_path'])
    try:
        host = cfg['host']
        connect_host = host.split('%')[0] if '%' in host else host
        iface  = host.split('%')[1] if '%' in host else 'en6'
        user   = cfg['user']
        pw     = cfg['password']
        src    = str(PROJECT_DIR)
        exclude = "--exclude='.git' --exclude='.DS_Store' --exclude='._*' --exclude='__pycache__'"
        cmd = (
            f"cd '{src}' && tar -czf - {exclude} . | "
            f"sshpass -p '{pw}' ssh -6 -o StrictHostKeyChecking=no "
            f"'{user}@{connect_host}%{iface}' "
            f"\"tar -xzf - -C {rpi_path} && find {rpi_path} -name '._*' -delete\""
        )
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            push_log("Деплой завершён ✓", "ok")
            return jsonify(ok=True, msg="Код загружен успешно ✓")
        return jsonify(ok=False, msg=r.stderr[:200])
    except Exception as e:
        return jsonify(ok=False, msg=str(e))


@app.route('/api/system-start', methods=['POST'])
def api_system_start():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    ssh_sudo("systemctl start oiynup")
    out, _ = ssh_run("systemctl is-active oiynup")
    return jsonify(ok=True, msg=f"Сервис: {out.strip()}")


@app.route('/api/system-stop', methods=['POST'])
def api_system_stop():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    ssh_sudo("systemctl stop oiynup")
    return jsonify(ok=True, msg="Сервис остановлен")


@app.route('/api/cam-capture', methods=['POST'])
def api_cam_capture():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    cmd = (
        'python3 -c "'
        'from picamera2 import Picamera2; import io,base64,sys\n'
        'cam=Picamera2()\n'
        'cam.configure(cam.create_still_configuration(main={\"size\":(640,480)}))\n'
        'cam.start(); import time; time.sleep(1)\n'
        'buf=io.BytesIO(); cam.capture_file(buf,format=\"jpeg\"); cam.close()\n'
        'sys.stdout.buffer.write(base64.b64encode(buf.getvalue()))\n'
        '"'
    )
    out, err = ssh_run(cmd, timeout=15)
    if out and out.strip():
        return jsonify(ok=True, image=out.strip())
    return jsonify(ok=False, msg=err[:150] or 'Нет данных от камеры')


@app.route('/api/mic-record', methods=['POST'])
def api_mic_record():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    import time

    # Пишем python скрипт на RPi — избегаем проблем с кавычками в SSH
    # Скрипт: нормализация до максимума + сохранение в браузерный формат
    script = (
        "import wave, numpy as np\n"
        "with wave.open('/tmp/oiynup_mic.wav') as f:\n"
        "    d = f.readframes(f.getnframes())\n"
        "    rate = f.getframerate()\n"
        "s = np.frombuffer(d, dtype=np.int32)\n"
        "left = s[0::2].astype(np.float32) / 2147483648.0\n"
        "# Нормализация: поднимаем до максимально возможной громкости\n"
        "peak = np.abs(left).max()\n"
        "if peak > 0.001:\n"
        "    left = left / peak * 0.95\n"
        "s16 = (left * 32767).astype(np.int16)\n"
        "rms = float(np.sqrt(np.mean(left**2)))\n"
        "with wave.open('/tmp/oiynup_play.wav', 'w') as f:\n"
        "    f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)\n"
        "    f.writeframes(s16.tobytes())\n"
        "print(int(min(100, rms * 300)))\n"
    )
    ssh_run(f"cat > /tmp/mic_process.py << 'PYEOF'\n{script}\nPYEOF")

    # Останавливаем сервис и сразу записываем
    ssh_sudo("systemctl stop oiynup", timeout=8)

    out, err = ssh_run(
        "arecord -D hw:0,0 -c2 -r48000 -f S32_LE -d5 /tmp/oiynup_mic.wav 2>&1"
        " && python3 /tmp/mic_process.py",
        timeout=16,
    )

    ssh_sudo("systemctl start oiynup", timeout=5)

    try:
        level = int(out.strip().splitlines()[-1])
    except Exception:
        level = 0
        push_log(f"Mic err: {err[:120]}", "err")

    return jsonify(ok=True, level=level, msg=f"Уровень: {level}%")


@app.route('/api/mic-audio')
def api_mic_audio():
    """Скачать обработанный WAV с RPi и отдать браузеру для воспроизведения."""
    if not is_connected():
        return "no connection", 503
    try:
        sftp = ssh_client.open_sftp()
        buf = io.BytesIO()
        sftp.getfo('/tmp/oiynup_play.wav', buf)
        sftp.close()
        buf.seek(0)
        return Response(
            buf.read(),
            mimetype='audio/wav',
            headers={
                'Content-Disposition': 'inline; filename="mic_recording.wav"',
                'Cache-Control': 'no-cache',
            }
        )
    except Exception as exc:
        return str(exc), 500


@app.route('/api/mic-play', methods=['POST'])
def api_mic_play():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    import time

    # Скрипт: усиление x8, конвертация стерео→моно, сохраняем 48kHz (без ресемплинга)
    script = (
        "import wave, numpy as np\n"
        "with wave.open('/tmp/oiynup_mic.wav') as f:\n"
        "    d = f.readframes(f.getnframes())\n"
        "    rate = f.getframerate()\n"
        "s = np.frombuffer(d, dtype=np.int32)\n"
        "left = s[0::2].astype(np.float32) / 2147483648.0\n"
        "left = np.clip(left * 8.0, -1.0, 1.0)\n"
        "s16 = (left * 32767).astype(np.int16)\n"
        "with wave.open('/tmp/oiynup_play.wav', 'w') as f:\n"
        "    f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)\n"
        "    f.writeframes(s16.tobytes())\n"
    )
    ssh_run(f"cat > /tmp/mic_play.py << 'PYEOF'\n{script}\nPYEOF")
    ssh_run("python3 /tmp/mic_play.py 2>&1", timeout=8)

    ssh_sudo("systemctl stop oiynup", timeout=6)
    ssh_run("aplay -D plughw:0,0 -q /tmp/oiynup_play.wav 2>&1", timeout=15)
    ssh_sudo("systemctl start oiynup", timeout=5)
    return jsonify(ok=True, msg="Воспроизведено ✓")


@app.route('/api/speaker-speak', methods=['POST'])
def api_speaker_speak():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    text = request.json.get('text', 'Привет').replace("'", "").replace('"', '')
    out, err = ssh_run(
        f"espeak-ng -v ru --stdout '{text}' 2>/dev/null | aplay -D plughw:0,0 -q 2>&1",
        timeout=12,
    )
    ok = not err or 'error' not in err.lower()
    return jsonify(ok=ok, msg=f"TTS: «{text}»" if ok else f"Ошибка: {err[:80]}")


@app.route('/api/speaker-sine', methods=['POST'])
def api_speaker_sine():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    # Используем speaker через сервис (espeak пишет через audio_output.py → aplay plughw)
    # Или напрямую если сервис остановлен
    out, err = ssh_run(
        'python3 -c "'
        'import wave,numpy as np\n'
        'sr=48000;t=np.linspace(0,1,sr,endpoint=False)\n'
        's=(np.sin(2*np.pi*800*t)*0.5*32767).astype(np.int16)\n'
        'st=np.column_stack([s,s]).flatten()\n'
        'with wave.open(\"/tmp/sine.wav\",\"w\") as f:\n'
        '    f.setnchannels(2);f.setsampwidth(2);f.setframerate(sr)\n'
        '    f.writeframes(st.tobytes())\n'
        '" && aplay -D plughw:0,0 -q /tmp/sine.wav 2>&1',
        timeout=8,
    )
    if err and 'error' in err.lower():
        return jsonify(ok=False, msg=f"Ошибка: {err[:100]}")
    return jsonify(ok=True, msg="Синус-тест ✓ (должен быть звук из динамика)")


@app.route('/api/gsm-signal', methods=['POST'])
def api_gsm_signal():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    cmd = (
        'python3 -c "'
        'import serial,time\n'
        'try:\n'
        '    s=serial.Serial(\"/dev/ttyS0\",9600,timeout=3)\n'
        '    s.write(b\"AT+CSQ\\r\\n\"); time.sleep(1.2)\n'
        '    r=s.read_all().decode(\"utf-8\",\"replace\"); s.close(); print(r)\n'
        'except Exception as e: print(\"ERR:\"+str(e))\n'
        '"'
    )
    out, _ = ssh_run(cmd, timeout=10)
    signal = 0
    if '+CSQ:' in out:
        try:
            signal = int(out.split('+CSQ:')[1].strip().split(',')[0])
        except Exception:
            pass
    if signal == 99 or signal == 0:
        text = 'Нет сигнала' if signal == 99 else 'SIM900 не отвечает'
    elif signal < 10:
        text = f'Слабый ({signal}/31)'
    else:
        text = f'Сигнал {signal}/31  ' + '█' * (signal // 5)
    return jsonify(ok=True, signal=signal, text=text)


@app.route('/api/gsm-sms', methods=['POST'])
def api_gsm_sms():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    phone = request.json.get('phone', '').strip()
    text  = request.json.get('text', '').strip()
    if not phone or not text:
        return jsonify(ok=False, msg='Заполни номер и текст')
    cfg['parent_phone'] = phone; save_cfg()
    encoded = text.encode('utf-16-be').hex().upper()
    cmd = (
        'python3 -c "'
        'import serial,time\n'
        's=serial.Serial(\"/dev/ttyS0\",9600,timeout=5)\n'
        'def at(c,w=1):\n'
        '    s.write((c+\"\\r\\n\").encode()); time.sleep(w)\n'
        '    return s.read_all().decode(\"utf-8\",\"replace\")\n'
        'at(\"AT\"); at(\"AT+CMGF=1\"); at(\"AT+CSCS=\\\"UCS2\\\"\")\n'
        f's.write(b\"AT+CMGS=\\\"{phone}\\\"\\r\"); time.sleep(.5)\n'
        f's.write(b\"{encoded}\\x1a\"); time.sleep(4)\n'
        'r=s.read_all().decode(\"utf-8\",\"replace\"); s.close()\n'
        'print(\"OK\" if \"+CMGS:\" in r else \"FAIL:\"+r[:40])\n'
        '"'
    )
    out, _ = ssh_run(cmd, timeout=20)
    ok = 'OK' in out
    return jsonify(ok=ok, msg='SMS отправлена ✓' if ok else f'Ошибка: {out.strip()[:60]}')


@app.route('/api/logs-fetch', methods=['POST'])
def api_logs_fetch():
    if not is_connected():
        return jsonify(ok=False, msg='Нет подключения')
    out, _ = ssh_run(
        "journalctl -u oiynup -n 80 --no-pager 2>/dev/null || "
        "tail -80 /var/log/oiynup.log 2>/dev/null || echo 'Лог пуст'",
        timeout=10)
    return jsonify(ok=True, lines=out.splitlines())


@app.route('/api/log-stream')
def api_log_stream():
    def gen():
        while True:
            try:
                item = log_queue.get(timeout=20)
                yield f"data: {json.dumps(item)}\n\n"
            except Empty:
                yield "data: {\"ts\":\"\",\"msg\":\"ping\",\"level\":\"dim\"}\n\n"
    return Response(gen(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ── Запуск ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import webbrowser
    print("\n" + "="*50)
    print("  Oiynup Control Panel")
    print("  http://localhost:7777")
    print("="*50 + "\n")
    threading.Timer(1.2, lambda: webbrowser.open('http://localhost:7777')).start()
    app.run(host='127.0.0.1', port=7777, debug=False, threaded=True)
