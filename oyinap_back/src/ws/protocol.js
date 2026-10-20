const { v4: uuidv4 } = require('uuid');

// ─── Исходящие команды к RPi ──────────────────────────────────────────────

function cmdSpeak(text, audioBuf = null, priority = 5) {
  const msg = { type: 'speak', id: uuidv4().slice(0, 8), priority };
  if (audioBuf) {
    msg.audio = audioBuf.toString('base64');
  } else {
    msg.text = text;
  }
  return JSON.stringify(msg);
}

function cmdDisplay(animation, color = [0, 100, 255], durationSec = 2.0) {
  return JSON.stringify({
    type: 'display',
    id: uuidv4().slice(0, 8),
    display: { animation, color, duration_sec: durationSec },
  });
}

function cmdSms(text, phone = null) {
  const msg = { type: 'sms', id: uuidv4().slice(0, 8), text };
  if (phone) msg.phone = phone;
  return JSON.stringify(msg);
}

function cmdIdle() {
  return JSON.stringify({ type: 'idle', id: uuidv4().slice(0, 8) });
}

function cmdPing() {
  return JSON.stringify({ type: 'ping', id: uuidv4().slice(0, 8), timestamp: Date.now() / 1000 });
}

// ─── Парсинг входящих сообщений от RPi ────────────────────────────────────

function parseMessage(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

module.exports = { cmdSpeak, cmdDisplay, cmdSms, cmdIdle, cmdPing, parseMessage };
