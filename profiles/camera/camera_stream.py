#!/usr/bin/env python3
"""
BearBox Camera — Flask Stream

Endpoints:
    GET  /             — main UI page
    GET  /stream       — main UI page
    GET  /feed         — raw MJPEG feed
    GET  /status       — JSON status
    GET  /log          — JSON array of last 20 entries
    POST /capture/now  — manual send trigger
    POST /capture/auto — toggle auto mode on/off
"""

import cv2
import time
import threading
import datetime
from flask import Flask, Response, jsonify, request, redirect

import profiles.camera.camera_sender as _sender_mod

app    = Flask(__name__)
_state = None
_log   = None

# Capture timer — set when capture is fired, cleared when description arrives
_capture_start_ts = None
_capture_lock     = threading.Lock()


# ── MJPEG feed ─────────────────────────────────────────────────

def _generate():
    while True:
        frame = _state.get_stream_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" +
               buf.tobytes() + b"\r\n")


@app.route("/feed")
def feed():
    return Response(
        _generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ── Status ─────────────────────────────────────────────────────

@app.route("/status")
def status():
    s = _state.get_status()

    # Calculate elapsed time if a capture is in progress
    with _capture_lock:
        elapsed = None
        if _capture_start_ts is not None:
            elapsed = round(time.time() - _capture_start_ts, 1)

    return jsonify({
        "motion":             s["motion"],
        "motion_count":       s["motion_count"],
        "fps":                s["fps"],
        "last_motion":        s["last_motion"],
        "ai_status":          s["ai_status"],
        "latest_description": s["latest_description"],
        "auto_enabled":       _sender_mod.auto_enabled,
        "capture_elapsed":    elapsed,   # seconds since capture fired, or null
    })


# ── Capture controls ───────────────────────────────────────────

@app.route("/capture/now", methods=["POST"])
def capture_now():
    global _capture_start_ts
    with _capture_lock:
        _capture_start_ts = time.time()
    _sender_mod.manual_trigger = True
    return jsonify({"ok": True, "message": "Manual capture queued"})


@app.route("/capture/auto", methods=["POST"])
def capture_auto():
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        _sender_mod.auto_enabled = bool(data["enabled"])
    else:
        _sender_mod.auto_enabled = not _sender_mod.auto_enabled
    print(f"[stream] Auto capture {'ON' if _sender_mod.auto_enabled else 'OFF'}")
    return jsonify({"ok": True, "auto_enabled": _sender_mod.auto_enabled})


# ── Log ────────────────────────────────────────────────────────

@app.route("/log")
def log_json():
    entries = _log.get_all()
    return jsonify([{
        "timestamp":   e["timestamp"],
        "time_str":    _fmt_ts(e["timestamp"]),
        "description": e["description"],
        "thumb_b64":   e["thumb_b64"],
        "tag":         e["tag"],
        "elapsed":     e.get("elapsed"),   # seconds the inference took
    } for e in entries])


@app.route("/log/ui")
def log_ui():
    return redirect("/stream", code=302)


# ── Main UI ────────────────────────────────────────────────────

_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BearBox — Camera</title>
<style>
  :root {
    --bg:        #00050f;
    --panel:     #050f1e;
    --amber:     #ffb000;
    --dimamber:  #784600;
    --darkamber: #140a00;
    --white:     #f0f8ff;
    --dimwhite:  #647891;
    --red:       #ff3232;
    --green:     #00ff50;
    --border:    #1a0e00;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--white);
    font-family: 'Courier New', Courier, monospace;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  body::before {
    content: '';
    position: fixed; inset: 0;
    background: repeating-linear-gradient(
      to bottom,
      transparent 0px, transparent 3px,
      rgba(0,0,0,0.12) 3px, rgba(0,0,0,0.12) 4px
    );
    pointer-events: none;
    z-index: 200;
  }

  header {
    background: var(--panel);
    border-bottom: 1px solid var(--dimamber);
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  header h1 {
    font-size: 1rem; font-weight: bold;
    color: var(--amber); letter-spacing: 0.15em; text-transform: uppercase;
  }
  .live-badge { font-size: 0.7rem; color: var(--dimwhite); }
  .live-badge span { color: var(--green); margin-right: 4px; }

  .video-section {
    background: #000;
    display: flex; justify-content: center; align-items: center;
    border-bottom: 2px solid var(--dimamber);
    position: relative; flex-shrink: 0;
  }
  .video-section img {
    display: block; max-width: 100%; max-height: 60vh;
    width: auto; height: auto;
  }
  .video-section.motion-active { box-shadow: inset 0 0 0 3px var(--red); }

  .controls {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 20px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap; flex-shrink: 0;
  }
  .controls-label {
    font-size: 0.7rem; color: var(--dimamber);
    text-transform: uppercase; letter-spacing: 0.08em;
  }
  .toggle-wrap { display: flex; align-items: center; gap: 8px; }
  .toggle-label { font-size: 0.76rem; min-width: 72px; }
  .toggle-label.on  { color: var(--green); }
  .toggle-label.off { color: var(--dimwhite); }

  input[type=checkbox] { display: none; }
  .toggle-switch {
    width: 36px; height: 18px;
    background: var(--darkamber);
    border: 1px solid var(--dimamber);
    border-radius: 9px; cursor: pointer;
    position: relative; transition: background 0.2s;
  }
  .toggle-switch::after {
    content: ''; position: absolute;
    width: 12px; height: 12px;
    background: var(--dimamber); border-radius: 50%;
    top: 2px; left: 2px; transition: left 0.2s, background 0.2s;
  }
  input[type=checkbox]:checked + .toggle-switch {
    background: #003820; border-color: var(--green);
  }
  input[type=checkbox]:checked + .toggle-switch::after {
    left: 20px; background: var(--green);
  }

  .btn {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.76rem; padding: 6px 14px;
    border: 1px solid var(--dimamber);
    background: var(--darkamber); color: var(--amber);
    cursor: pointer; letter-spacing: 0.05em; text-transform: uppercase;
    transition: background 0.15s, border-color 0.15s;
  }
  .btn:hover:not(:disabled) { background: #2a1400; border-color: var(--amber); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .status-bar {
    display: flex; gap: 20px;
    padding: 8px 20px;
    background: var(--darkamber);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap; flex-shrink: 0;
  }
  .stat { font-size: 0.72rem; }
  .stat .lbl { color: var(--dimamber); margin-right: 4px; }
  .stat .val { color: var(--white); }
  .stat .val.red   { color: var(--red); }
  .stat .val.amber { color: var(--amber); }
  .stat .val.green { color: var(--green); }

  .description-bar {
    padding: 8px 20px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    font-size: 0.75rem; color: var(--dimwhite);
    flex-shrink: 0; min-height: 34px;
  }
  .description-bar .lbl { color: var(--dimamber); margin-right: 6px; }
  .description-bar .txt { color: var(--white); }

  .log-section { flex: 1; overflow-y: auto; padding: 16px 20px; }
  .log-header {
    display: flex; justify-content: space-between;
    align-items: center; margin-bottom: 12px;
  }
  .log-title {
    font-size: 0.8rem; color: var(--amber);
    letter-spacing: 0.1em; text-transform: uppercase;
  }
  .log-meta { font-size: 0.68rem; color: var(--dimwhite); }

  .entry {
    display: flex; gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .thumb {
    width: 80px; height: 45px; flex-shrink: 0;
    background: #000; border: 1px solid var(--border);
    overflow: hidden; display: flex;
    align-items: center; justify-content: center;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .no-thumb  { font-size: 0.6rem; color: var(--dimamber); text-align: center; }

  .entry-body { flex: 1; min-width: 0; }
  .entry-meta {
    font-size: 0.68rem; color: var(--dimwhite);
    margin-bottom: 4px;
    display: flex; align-items: center; gap: 6px;
  }
  .entry-elapsed {
    font-size: 0.6rem; color: var(--dimamber);
    margin-left: auto;
  }
  .entry-description {
    font-size: 0.78rem; color: var(--white);
    line-height: 1.45; word-break: break-word;
  }
  .entry-description.error { color: var(--red); }

  .tag-manual {
    font-size: 0.6rem; padding: 1px 5px;
    border: 1px solid var(--amber); color: var(--amber);
    letter-spacing: 0.05em;
  }
  .tag-error {
    font-size: 0.6rem; padding: 1px 5px;
    border: 1px solid var(--red); color: var(--red);
    letter-spacing: 0.05em;
  }

  .empty {
    color: var(--dimwhite); font-size: 0.8rem;
    text-align: center; padding: 40px 0; line-height: 1.8;
  }

  .toast {
    position: fixed; bottom: 20px; right: 20px;
    padding: 8px 16px; font-size: 0.76rem;
    border-radius: 2px; opacity: 0;
    transition: opacity 0.2s; z-index: 999; pointer-events: none;
  }
  .toast.show { opacity: 1; }
  .toast.ok   { background: #003820; border: 1px solid var(--green); color: var(--green); }
  .toast.warn { background: #1a0e00; border: 1px solid var(--amber); color: var(--amber); }
  .toast.err  { background: #1a0000; border: 1px solid var(--red);   color: var(--red);   }

  /* timer pill shown next to button while sending */
  .capture-timer {
    font-size: 0.72rem; color: var(--amber);
    display: none;
  }
  .capture-timer.active { display: inline; }
</style>
</head>
<body>

<header>
  <h1>BearBox — Camera</h1>
  <div class="live-badge"><span>●</span> LIVE</div>
</header>

<div class="video-section" id="video-section">
  <img src="/feed" alt="camera feed">
</div>

<div class="controls">
  <span class="controls-label">AI Auto</span>
  <div class="toggle-wrap">
    <input type="checkbox" id="auto-toggle"
           onchange="toggleAuto(this.checked)" __AUTO_CHECKED__>
    <label class="toggle-switch" for="auto-toggle"></label>
    <span class="toggle-label __AUTO_CLASS__" id="auto-label">__AUTO_TEXT__</span>
  </div>
  <button class="btn" id="btn-manual" onclick="manualCapture()">▶ Capture Now</button>
  <span class="capture-timer" id="capture-timer">⏱ <span id="timer-val">0</span>s</span>
</div>

<div class="status-bar">
  <div class="stat">
    <span class="lbl">AI</span>
    <span class="val amber" id="s-aistatus">__AI_STATUS__</span>
  </div>
  <div class="stat">
    <span class="lbl">FPS</span>
    <span class="val" id="s-fps">__FPS__</span>
  </div>
  <div class="stat">
    <span class="lbl">MOTION</span>
    <span class="val __MC_CLASS__" id="s-motion">__MOTION_COUNT__ events</span>
  </div>
</div>

<div class="description-bar">
  <span class="lbl">LAST DESCRIPTION</span>
  <span class="txt" id="s-description">__LATEST_DESCRIPTION__</span>
</div>

<div class="log-section">
  <div class="log-header">
    <div class="log-title" id="log-count">Caption Log — __ENTRY_COUNT__ entries (newest first)</div>
    <div class="log-meta" id="last-refresh">loaded __LOAD_TIME__</div>
  </div>
  <div id="log-rows">__LOG_ROWS__</div>
</div>

<div class="toast" id="toast"></div>

<script>
  let _toastTimer;

  function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className   = 'toast show ' + type;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => t.className = 'toast', 2800);
  }

  function toggleAuto(checked) {
    const label = document.getElementById('auto-label');
    label.textContent = checked ? 'AUTO ON' : 'AUTO OFF';
    label.className   = 'toggle-label ' + (checked ? 'on' : 'off');
    fetch('/capture/auto', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled: checked})
    })
    .then(r => r.json())
    .then(d => showToast(d.auto_enabled ? 'Auto ON' : 'Auto OFF',
                         d.auto_enabled ? 'ok' : 'warn'))
    .catch(() => showToast('Toggle failed', 'err'));
  }

  // ── Capture timer ───────────────────────────────────────────
  let _captureStarted  = null;
  let _timerInterval   = null;
  let _captureCooldown = false;

  function startCaptureTimer() {
    _captureStarted = Date.now();
    const timerEl   = document.getElementById('capture-timer');
    const valEl     = document.getElementById('timer-val');
    timerEl.classList.add('active');
    _timerInterval = setInterval(() => {
      const secs = ((Date.now() - _captureStarted) / 1000).toFixed(1);
      valEl.textContent = secs;
    }, 100);
  }

  function stopCaptureTimer() {
    clearInterval(_timerInterval);
    const timerEl = document.getElementById('capture-timer');
    timerEl.classList.remove('active');
    _captureStarted = null;
  }

  function manualCapture() {
    if (_captureCooldown) { showToast('Cooldown active — wait', 'warn'); return; }
    const btn = document.getElementById('btn-manual');
    btn.disabled    = true;
    btn.textContent = '⏳ Sending...';
    fetch('/capture/now', {method: 'POST'})
      .then(r => r.json())
      .then(() => {
        showToast('Frame sent to laptop...', 'ok');
        startCaptureTimer();
        _captureCooldown = true;
        setTimeout(() => {
          _captureCooldown    = false;
          btn.disabled        = false;
          btn.textContent     = '▶ Capture Now';
          stopCaptureTimer();
        }, 15000);
      })
      .catch(() => {
        showToast('Capture failed', 'err');
        btn.disabled    = false;
        btn.textContent = '▶ Capture Now';
        stopCaptureTimer();
      });
  }

  // ── Status polling ──────────────────────────────────────────
  let _lastAiStatus = '';

  function refreshStatus() {
    fetch('/status')
      .then(r => r.json())
      .then(s => {
        const ai = document.getElementById('s-aistatus');
        if (ai) ai.textContent = s.ai_status || 'IDLE';

        // Stop timer when AI status leaves SENDING...
        if (_lastAiStatus === 'SENDING...' && s.ai_status !== 'SENDING...') {
          stopCaptureTimer();
        }
        _lastAiStatus = s.ai_status;

        const fps = document.getElementById('s-fps');
        if (fps) fps.textContent = s.fps;

        const mc = document.getElementById('s-motion');
        if (mc) {
          mc.textContent = s.motion_count + ' events';
          mc.className   = 'val ' + (s.motion_count > 0 ? 'red' : '');
        }

        const desc = document.getElementById('s-description');
        if (desc && s.latest_description) {
          const txt = s.latest_description;
          desc.textContent = txt.length > 120 ? txt.slice(0, 117) + '...' : txt;
        }

        const vs = document.getElementById('video-section');
        if (vs) {
          if (s.motion) vs.classList.add('motion-active');
          else          vs.classList.remove('motion-active');
        }

        const toggle = document.getElementById('auto-toggle');
        if (toggle && toggle.checked !== s.auto_enabled) {
          toggle.checked = s.auto_enabled;
          const label    = document.getElementById('auto-label');
          label.textContent = s.auto_enabled ? 'AUTO ON' : 'AUTO OFF';
          label.className   = 'toggle-label ' + (s.auto_enabled ? 'on' : 'off');
        }
      })
      .catch(() => {});
  }

  function refreshLog() {
    fetch('/log')
      .then(r => r.json())
      .then(entries => {
        document.getElementById('last-refresh').textContent =
          'refreshed ' + new Date().toLocaleTimeString();
        document.getElementById('log-count').textContent =
          'Caption Log — ' + entries.length + ' entries (newest first)';

        const container = document.getElementById('log-rows');
        if (entries.length === 0) {
          container.innerHTML =
            '<div class="empty">No descriptions yet.<br>Waiting for motion or manual capture...</div>';
          return;
        }

        container.innerHTML = entries.map(e => {
          const isError   = e.tag === 'error';
          const descClass = isError ? 'entry-description error' : 'entry-description';
          let tagHtml = '';
          if (e.tag === 'manual') tagHtml = '<span class="tag-manual">MANUAL</span>';
          if (e.tag === 'error')  tagHtml = '<span class="tag-error">ERROR</span>';

          // Show elapsed time if available
          const elapsedHtml = e.elapsed
            ? '<span class="entry-elapsed">' + e.elapsed.toFixed(1) + 's</span>'
            : '';

          const thumb = e.thumb_b64
            ? '<img src="data:image/jpeg;base64,' + e.thumb_b64 + '" alt="frame">'
            : '<div class="no-thumb">no<br>frame</div>';
          return (
            '<div class="entry">' +
              '<div class="thumb">' + thumb + '</div>' +
              '<div class="entry-body">' +
                '<div class="entry-meta">' + e.time_str + tagHtml + elapsedHtml + '</div>' +
                '<div class="' + descClass + '">' + e.description + '</div>' +
              '</div>' +
            '</div>'
          );
        }).join('');
      })
      .catch(() => {});
  }

  setInterval(refreshStatus, 2000);
  setInterval(refreshLog,    5000);
</script>
</body>
</html>
"""


def _fmt_ts(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _render_page():
    s       = _state.get_status()
    entries = _log.get_all()

    if not entries:
        rows_html = '<div class="empty">No descriptions yet.<br>Waiting for motion or manual capture...</div>'
    else:
        rows = []
        for e in entries:
            is_error  = e["tag"] == "error"
            desc_cls  = "entry-description error" if is_error else "entry-description"
            tag_html  = ""
            if e["tag"] == "manual":
                tag_html = '<span class="tag-manual">MANUAL</span>'
            elif e["tag"] == "error":
                tag_html = '<span class="tag-error">ERROR</span>'
            elapsed_html = (
                f'<span class="entry-elapsed">{e["elapsed"]:.1f}s</span>'
                if e.get("elapsed") else ""
            )
            thumb_html = (
                f'<img src="data:image/jpeg;base64,{e["thumb_b64"]}" alt="frame">'
                if e["thumb_b64"] else '<div class="no-thumb">no<br>frame</div>'
            )
            rows.append(
                f'<div class="entry">'
                f'<div class="thumb">{thumb_html}</div>'
                f'<div class="entry-body">'
                f'<div class="entry-meta">{_fmt_ts(e["timestamp"])}{tag_html}{elapsed_html}</div>'
                f'<div class="{desc_cls}">{e["description"]}</div>'
                f'</div></div>'
            )
        rows_html = "\n".join(rows)

    mc          = s.get("motion_count", 0)
    mc_class    = "val red" if mc > 0 else "val"
    latest_desc = s.get("latest_description") or "none yet"
    if len(latest_desc) > 120:
        latest_desc = latest_desc[:117] + "..."

    auto_checked = "checked" if _sender_mod.auto_enabled else ""
    auto_text    = "AUTO ON" if _sender_mod.auto_enabled else "AUTO OFF"
    auto_class   = "on" if _sender_mod.auto_enabled else "off"

    html = _PAGE_HTML
    html = html.replace("__AI_STATUS__",          s.get("ai_status", "IDLE"))
    html = html.replace("__MOTION_COUNT__",        str(mc))
    html = html.replace("__MC_CLASS__",            mc_class)
    html = html.replace("__FPS__",                 str(s.get("fps", 0.0)))
    html = html.replace("__ENTRY_COUNT__",         str(len(entries)))
    html = html.replace("__LOG_ROWS__",            rows_html)
    html = html.replace("__LOAD_TIME__",           datetime.datetime.now().strftime("%H:%M:%S"))
    html = html.replace("__LATEST_DESCRIPTION__",  latest_desc)
    html = html.replace("__AUTO_CHECKED__",        auto_checked)
    html = html.replace("__AUTO_TEXT__",           auto_text)
    html = html.replace("__AUTO_CLASS__",          auto_class)
    return html


@app.route("/")
@app.route("/stream")
def main_ui():
    return Response(_render_page(), mimetype="text/html")


def start_stream(state, log, port=80):
    global _state, _log
    _state = state
    _log   = log

    t = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=port, debug=False, use_reloader=False
        ),
        daemon=True,
    )
    t.start()
    print(f"[stream] Flask running on port {port}")
    return t