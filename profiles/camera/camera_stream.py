#!/usr/bin/env python3
"""
BearBox Camera — Flask Stream

MJPEG stream server + AI caption log UI.

Endpoints:
    GET  /stream        — MJPEG live stream
    GET  /status        — JSON motion + caption status
    GET  /log           — JSON array of last 20 caption entries
    GET  /log/ui        — Amber-themed HTML log page (auto-refreshes)
    POST /capture/now   — Manually trigger a single AI caption job
    POST /capture/auto  — Toggle automatic motion captioning on/off
"""

import cv2
import time
import threading
import datetime
from flask import Flask, Response, jsonify, request

import profiles.camera.camera_caption as _caption_mod

app = Flask(__name__)

_state = None   # DetectionState — set by start_stream()
_log   = None   # CaptionLog    — set by start_stream()


# ── MJPEG stream ──────────────────────────────────────────────

def _generate():
    while True:
        frame = _state.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" +
               buf.tobytes() + b"\r\n")


@app.route("/stream")
def stream():
    return Response(
        _generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ── Status JSON ───────────────────────────────────────────────

@app.route("/status")
def status():
    s = _state.get_status()
    return jsonify({
        "motion":          s["motion"],
        "motion_count":    s["motion_count"],
        "fps":             s["fps"],
        "last_motion":     s["last_motion"],
        "caption_status":  s["caption_status"],
        "latest_caption":  s["latest_caption"],
        "auto_enabled":    _caption_mod.auto_enabled,
    })


# ── Caption controls ──────────────────────────────────────────

@app.route("/capture/now", methods=["POST"])
def capture_now():
    """Fire a single manual caption job."""
    _caption_mod.manual_trigger = True
    return jsonify({"ok": True, "message": "Manual capture queued"})


@app.route("/capture/auto", methods=["POST"])
def capture_auto():
    """Toggle automatic motion captioning on or off."""
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        _caption_mod.auto_enabled = bool(data["enabled"])
    else:
        _caption_mod.auto_enabled = not _caption_mod.auto_enabled
    state_str = "ON" if _caption_mod.auto_enabled else "OFF"
    print(f"[stream] Auto capture toggled {state_str}")
    return jsonify({"ok": True, "auto_enabled": _caption_mod.auto_enabled})


# ── Caption log JSON ──────────────────────────────────────────

@app.route("/log")
def log_json():
    entries = _log.get_all()
    out = []
    for e in entries:
        out.append({
            "timestamp":  e["timestamp"],
            "time_str":   _fmt_ts(e["timestamp"]),
            "caption":    e["caption"],
            "thumb_b64":  e["thumb_b64"],
        })
    return jsonify(out)


# ── Caption log HTML UI ───────────────────────────────────────

_LOG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BearBox — Motion Log</title>
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
  }

  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
      to bottom,
      transparent 0px, transparent 3px,
      rgba(0,0,0,0.15) 3px, rgba(0,0,0,0.15) 4px
    );
    pointer-events: none;
    z-index: 100;
  }

  header {
    background: var(--panel);
    border-bottom: 1px solid var(--dimamber);
    padding: 14px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
  }

  header h1 {
    font-size: 1.05rem;
    font-weight: bold;
    color: var(--amber);
    letter-spacing: 0.15em;
    text-transform: uppercase;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }

  .live-badge {
    font-size: 0.72rem;
    color: var(--dimwhite);
  }

  .live-badge span {
    color: var(--green);
    margin-right: 5px;
  }

  /* ── Controls bar ── */
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 24px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }

  .controls-label {
    font-size: 0.72rem;
    color: var(--dimamber);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  /* Slider toggle */
  .toggle-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .toggle-wrap .toggle-label {
    font-size: 0.78rem;
    color: var(--dimwhite);
    min-width: 60px;
  }

  .toggle-wrap .toggle-label.on  { color: var(--amber); }
  .toggle-wrap .toggle-label.off { color: var(--dimwhite); }

  .switch {
    position: relative;
    display: inline-block;
    width: 44px;
    height: 24px;
    flex-shrink: 0;
  }

  .switch input { opacity: 0; width: 0; height: 0; }

  .slider {
    position: absolute;
    inset: 0;
    background: var(--darkamber);
    border: 1px solid var(--dimamber);
    border-radius: 24px;
    cursor: pointer;
    transition: background 0.2s;
  }

  .slider::before {
    content: '';
    position: absolute;
    width: 16px;
    height: 16px;
    left: 3px;
    top: 3px;
    background: var(--dimamber);
    border-radius: 50%;
    transition: transform 0.2s, background 0.2s;
  }

  input:checked + .slider {
    background: #3a2000;
    border-color: var(--amber);
  }

  input:checked + .slider::before {
    background: var(--amber);
    transform: translateX(20px);
  }

  /* Divider */
  .controls-divider {
    width: 1px;
    height: 24px;
    background: var(--border);
    margin: 0 2px;
  }

  /* Manual capture button */
  .btn-capture {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.78rem;
    font-weight: bold;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--bg);
    background: var(--amber);
    border: none;
    border-radius: 3px;
    padding: 6px 14px;
    cursor: pointer;
    transition: background 0.15s, opacity 0.15s;
  }

  .btn-capture:hover   { background: #ffc840; }
  .btn-capture:active  { background: var(--dimamber); color: var(--amber); }
  .btn-capture:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    background: var(--dimamber);
    color: var(--darkamber);
  }

  /* Feedback toast */
  .toast {
    font-size: 0.72rem;
    padding: 4px 10px;
    border-radius: 3px;
    opacity: 0;
    transition: opacity 0.3s;
    pointer-events: none;
  }
  .toast.show { opacity: 1; }
  .toast.ok   { color: var(--green);  background: rgba(0,255,80,0.08);  border: 1px solid rgba(0,255,80,0.2);  }
  .toast.warn { color: var(--amber);  background: rgba(255,176,0,0.08); border: 1px solid rgba(255,176,0,0.2); }
  .toast.err  { color: var(--red);    background: rgba(255,50,50,0.08); border: 1px solid rgba(255,50,50,0.2); }

  /* Status bar */
  .status-bar {
    margin: 12px 24px;
    padding: 8px 14px;
    background: var(--darkamber);
    border-left: 3px solid var(--amber);
    font-size: 0.78rem;
    color: var(--dimwhite);
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
  }

  .status-bar .lbl { color: var(--dimamber); margin-right: 5px; }
  .status-bar .val { color: var(--amber); }
  .status-bar .val.red   { color: var(--red); }
  .status-bar .val.green { color: var(--green); }

  /* Nav links */
  .nav-links {
    margin: 0 24px 12px;
    font-size: 0.75rem;
    color: var(--dimamber);
  }

  .nav-links a { color: var(--amber); text-decoration: none; }
  .nav-links a:hover { color: var(--white); }

  /* Log */
  .log-container { padding: 0 24px 32px; }

  .log-header {
    font-size: 0.68rem;
    color: var(--dimamber);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .empty {
    padding: 48px;
    text-align: center;
    color: var(--dimwhite);
    font-size: 0.85rem;
    line-height: 1.8;
  }

  .entry {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 12px 0;
    border-bottom: 1px solid var(--border);
  }

  .thumb {
    flex-shrink: 0;
    width: 96px;
    height: 54px;
    background: var(--darkamber);
    border: 1px solid var(--border);
    border-radius: 2px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .thumb .no-thumb {
    font-size: 0.58rem;
    color: var(--dimamber);
    text-align: center;
  }

  .entry-body { flex: 1; min-width: 0; }

  .entry-meta {
    font-size: 0.68rem;
    color: var(--dimamber);
    margin-bottom: 4px;
    display: flex;
    gap: 10px;
  }

  .entry-meta .tag-manual {
    color: var(--amber);
    border: 1px solid var(--dimamber);
    border-radius: 2px;
    padding: 0 4px;
    font-size: 0.62rem;
  }

  .entry-caption {
    font-size: 0.88rem;
    color: var(--white);
    line-height: 1.45;
    word-break: break-word;
  }

  .entry-caption.error { color: var(--red); font-style: italic; }
  .entry:first-child .entry-caption:not(.error) { color: var(--amber); }

  .refresh-note {
    text-align: center;
    font-size: 0.68rem;
    color: var(--dimamber);
    padding: 16px;
  }
</style>
</head>
<body>

<header>
  <h1>&#9654; BearBox &mdash; Motion Log</h1>
  <div class="header-right">
    <div class="live-badge"><span>&#9679;</span> LIVE</div>
  </div>
</header>

<!-- Controls -->
<div class="controls">
  <span class="controls-label">AI Capture</span>

  <!-- Slider toggle -->
  <div class="toggle-wrap">
    <span class="toggle-label" id="auto-label">AUTO ON</span>
    <label class="switch">
      <input type="checkbox" id="auto-toggle" checked onchange="toggleAuto(this.checked)">
      <span class="slider"></span>
    </label>
  </div>

  <div class="controls-divider"></div>

  <!-- Manual capture button -->
  <button class="btn-capture" id="btn-manual" onclick="manualCapture()">
    &#9654; Capture Now
  </button>

  <!-- Feedback toast -->
  <span class="toast" id="toast"></span>
</div>

<!-- Status -->
<div class="status-bar">
  <span><span class="lbl">AI STATUS</span><span class="val" id="s-capstat">__CAP_STATUS__</span></span>
  <span><span class="lbl">MOTION EVENTS</span><span class="val __MC_CLASS__">__MOTION_COUNT__</span></span>
  <span><span class="lbl">FPS</span><span class="val">__FPS__</span></span>
</div>

<!-- Nav -->
<div class="nav-links">
  <a href="/stream" target="_blank">/stream</a> &nbsp;|&nbsp;
  <a href="/status" target="_blank">/status</a> &nbsp;|&nbsp;
  <a href="/log"    target="_blank">/log</a>
</div>

<!-- Log -->
<div class="log-container">
  <div class="log-header">
    <span>Caption Log &mdash; last __ENTRY_COUNT__ entries (newest first)</span>
    <span id="last-refresh">loaded __LOAD_TIME__</span>
  </div>
  <div id="log-rows">__LOG_ROWS__</div>
</div>

<p class="refresh-note">Log refreshes every 5s &nbsp;&middot;&nbsp; controls take effect immediately</p>

<script>
  // ── State ──────────────────────────────────────────────────
  let autoEnabled = __AUTO_ENABLED_JS__;

  // ── Toast helper ──────────────────────────────────────────
  let _toastTimer = null;
  function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className   = 'toast show ' + type;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { t.className = 'toast'; }, 2800);
  }

  // ── Auto toggle ───────────────────────────────────────────
  function toggleAuto(checked) {
    autoEnabled = checked;
    const label = document.getElementById('auto-label');
    label.textContent = checked ? 'AUTO ON' : 'AUTO OFF';
    label.className   = 'toggle-label ' + (checked ? 'on' : 'off');

    fetch('/capture/auto', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled: checked})
    })
    .then(r => r.json())
    .then(d => {
      showToast(d.auto_enabled ? 'Auto capture ON' : 'Auto capture OFF',
                d.auto_enabled ? 'ok' : 'warn');
    })
    .catch(() => showToast('Toggle failed', 'err'));
  }

  // ── Manual capture ────────────────────────────────────────
  let _captureCooldown = false;

  function manualCapture() {
    if (_captureCooldown) {
      showToast('Cooldown active — please wait', 'warn');
      return;
    }

    const btn = document.getElementById('btn-manual');
    btn.disabled    = true;
    btn.textContent = '⏳ Capturing...';

    fetch('/capture/now', { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        showToast('Capture queued — processing...', 'ok');
        // disable button for cooldown duration
        _captureCooldown = true;
        setTimeout(() => {
          _captureCooldown    = false;
          btn.disabled        = false;
          btn.textContent     = '▶ Capture Now';
        }, 15000);
      })
      .catch(() => {
        showToast('Capture request failed', 'err');
        btn.disabled    = false;
        btn.textContent = '▶ Capture Now';
      });
  }

  // ── Live log refresh (every 5s) ───────────────────────────
  function refreshLog() {
    fetch('/log')
      .then(r => r.json())
      .then(entries => {
        const container = document.getElementById('log-rows');
        const countEl   = document.querySelector('.log-header span:first-child');
        const timeEl    = document.getElementById('last-refresh');

        timeEl.textContent = 'refreshed ' + new Date().toLocaleTimeString();
        countEl.textContent = 'Caption Log — last ' + entries.length + ' entries (newest first)';

        if (entries.length === 0) {
          container.innerHTML = '<div class="empty">No motion events captured yet.<br>Waiting for activity...</div>';
          return;
        }

        container.innerHTML = entries.map((e, i) => {
          const isManual = e.caption.startsWith('[manual]');
          const isError  = e.caption.startsWith('[error') || e.caption.startsWith('[model');
          const capText  = isManual ? e.caption.replace('[manual] ', '') : e.caption;
          const capClass = isError ? 'entry-caption error' : 'entry-caption';
          const tag      = isManual ? '<span class="tag-manual">MANUAL</span>' : '';

          const thumb = e.thumb_b64
            ? '<img src="data:image/jpeg;base64,' + e.thumb_b64 + '" alt="frame">'
            : '<div class="no-thumb">no frame</div>';

          return (
            '<div class="entry">' +
              '<div class="thumb">' + thumb + '</div>' +
              '<div class="entry-body">' +
                '<div class="entry-meta">' + e.time_str + tag + '</div>' +
                '<div class="' + capClass + '">' + capText + '</div>' +
              '</div>' +
            '</div>'
          );
        }).join('');
      })
      .catch(() => {});  // silently skip on network error
  }

  // ── Live status refresh (every 3s) ────────────────────────
  function refreshStatus() {
    fetch('/status')
      .then(r => r.json())
      .then(s => {
        const el = document.getElementById('s-capstat');
        if (el) el.textContent = s.caption_status || 'IDLE';

        // sync toggle if server state diverged (e.g. after reboot)
        const toggle = document.getElementById('auto-toggle');
        if (toggle && toggle.checked !== s.auto_enabled) {
          toggle.checked = s.auto_enabled;
          autoEnabled    = s.auto_enabled;
          const label    = document.getElementById('auto-label');
          label.textContent = s.auto_enabled ? 'AUTO ON' : 'AUTO OFF';
          label.className   = 'toggle-label ' + (s.auto_enabled ? 'on' : 'off');
        }
      })
      .catch(() => {});
  }

  // kick off refresh loops
  setInterval(refreshLog,    5000);
  setInterval(refreshStatus, 3000);
</script>

</body>
</html>
"""


def _fmt_ts(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _render_log_html():
    import profiles.camera.camera_caption as _cm
    s       = _state.get_status()
    entries = _log.get_all()

    if not entries:
        rows_html = '<div class="empty">No motion events captured yet.<br>Waiting for activity...</div>'
    else:
        rows = []
        for e in entries:
            is_manual = e["caption"].startswith("[manual]")
            is_err    = e["caption"].startswith("[error") or e["caption"].startswith("[model")
            cap_text  = e["caption"].replace("[manual] ", "") if is_manual else e["caption"]
            cap_cls   = "entry-caption error" if is_err else "entry-caption"
            tag       = '<span class="tag-manual">MANUAL</span>' if is_manual else ""

            if e["thumb_b64"]:
                thumb_html = f'<img src="data:image/jpeg;base64,{e["thumb_b64"]}" alt="frame">'
            else:
                thumb_html = '<div class="no-thumb">no frame</div>'

            rows.append(
                f'<div class="entry">'
                f'<div class="thumb">{thumb_html}</div>'
                f'<div class="entry-body">'
                f'<div class="entry-meta">{_fmt_ts(e["timestamp"])}{tag}</div>'
                f'<div class="{cap_cls}">{cap_text}</div>'
                f'</div></div>'
            )
        rows_html = "\n".join(rows)

    mc       = s.get("motion_count", 0)
    mc_class = "val red" if mc > 0 else "val"

    html = _LOG_HTML
    html = html.replace("__CAP_STATUS__",       s.get("caption_status", "IDLE"))
    html = html.replace("__MOTION_COUNT__",      str(mc))
    html = html.replace("__MC_CLASS__",          mc_class)
    html = html.replace("__FPS__",               str(s.get("fps", 0.0)))
    html = html.replace("__ENTRY_COUNT__",       str(len(entries)))
    html = html.replace("__LOG_ROWS__",          rows_html)
    html = html.replace("__AUTO_ENABLED_JS__",   "true" if _cm.auto_enabled else "false")
    html = html.replace("__LOAD_TIME__",         datetime.datetime.now().strftime("%H:%M:%S"))
    return html


@app.route("/log/ui")
def log_ui():
    return Response(_render_log_html(), mimetype="text/html")


# ── Start ─────────────────────────────────────────────────────

def start_stream(state, log, port=5000):
    """
    Start Flask in a daemon thread.
    state — DetectionState
    log   — CaptionLog
    port  — Flask port (default 5000)
    """
    global _state, _log
    _state = state
    _log   = log

    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port,
                               debug=False, use_reloader=False),
        daemon=True
    )
    t.start()
    print(f"[stream] Flask running on port {port}")
    print(f"[stream] Motion log UI at http://<ip>:{port}/log/ui")
    return t