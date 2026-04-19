#!/usr/bin/env python3
"""
BearBox Camera — Flask Stream

Single-page UI at / and /stream:
  - Live MJPEG video feed
  - AI capture controls (auto toggle + manual button)
  - Motion caption log (last 20 entries with thumbnails)

Endpoints:
    GET  /              — main UI page (same as /stream)
    GET  /stream        — main UI page
    GET  /feed          — raw MJPEG feed (used by the <img> tag on the page)
    GET  /status        — JSON motion + caption status
    GET  /log           — JSON array of last 20 caption entries
    GET  /log/ui        — redirects to /stream
    POST /capture/now   — manually trigger a single AI caption job
    POST /capture/auto  — toggle automatic motion captioning on/off
"""

import cv2
import time
import threading
import datetime
from flask import Flask, Response, jsonify, request, redirect

import profiles.camera.camera_caption as _caption_mod

app = Flask(__name__)

_state = None   # DetectionState — set by start_stream()
_log   = None   # CaptionLog    — set by start_stream()


# ── Raw MJPEG feed (used by <img src="/feed"> on the page) ───

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


@app.route("/feed")
def feed():
    return Response(
        _generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ── Status JSON ───────────────────────────────────────────────

@app.route("/status")
def status():
    s = _state.get_status()
    return jsonify({
        "motion":         s["motion"],
        "motion_count":   s["motion_count"],
        "fps":            s["fps"],
        "last_motion":    s["last_motion"],
        "caption_status": s["caption_status"],
        "latest_caption": s["latest_caption"],
        "auto_enabled":   _caption_mod.auto_enabled,
    })


# ── Caption controls ──────────────────────────────────────────

@app.route("/capture/now", methods=["POST"])
def capture_now():
    _caption_mod.manual_trigger = True
    return jsonify({"ok": True, "message": "Manual capture queued"})


@app.route("/capture/auto", methods=["POST"])
def capture_auto():
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        _caption_mod.auto_enabled = bool(data["enabled"])
    else:
        _caption_mod.auto_enabled = not _caption_mod.auto_enabled
    print(f"[stream] Auto capture {'ON' if _caption_mod.auto_enabled else 'OFF'}")
    return jsonify({"ok": True, "auto_enabled": _caption_mod.auto_enabled})


# ── Caption log JSON ──────────────────────────────────────────

@app.route("/log")
def log_json():
    entries = _log.get_all()
    return jsonify([{
        "timestamp":  e["timestamp"],
        "time_str":   _fmt_ts(e["timestamp"]),
        "caption":    e["caption"],
        "thumb_b64":  e["thumb_b64"],
    } for e in entries])


# ── /log/ui redirect ──────────────────────────────────────────

@app.route("/log/ui")
def log_ui():
    return redirect("/stream", code=302)


# ── Main UI page ──────────────────────────────────────────────

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

  /* scanlines */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
      to bottom,
      transparent 0px, transparent 3px,
      rgba(0,0,0,0.12) 3px, rgba(0,0,0,0.12) 4px
    );
    pointer-events: none;
    z-index: 200;
  }

  /* ── Header ── */
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
    font-size: 1rem;
    font-weight: bold;
    color: var(--amber);
    letter-spacing: 0.15em;
    text-transform: uppercase;
  }

  .live-badge {
    font-size: 0.7rem;
    color: var(--dimwhite);
  }
  .live-badge span { color: var(--green); margin-right: 4px; }

  /* ── Video section ── */
  .video-section {
    background: #000;
    display: flex;
    justify-content: center;
    align-items: center;
    border-bottom: 2px solid var(--dimamber);
    position: relative;
    flex-shrink: 0;
  }

  .video-section img {
    display: block;
    max-width: 100%;
    max-height: 60vh;
    width: auto;
    height: auto;
  }

  /* motion flash border on video */
  .video-section.motion-active {
    box-shadow: inset 0 0 0 3px var(--red);
  }

  /* ── Controls bar ── */
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
    flex-shrink: 0;
  }

  .controls-label {
    font-size: 0.7rem;
    color: var(--dimamber);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  /* slider toggle */
  .toggle-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .toggle-label {
    font-size: 0.76rem;
    min-width: 62px;
  }
  .toggle-label.on  { color: var(--amber); }
  .toggle-label.off { color: var(--dimwhite); }

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
    width: 16px; height: 16px;
    left: 3px; top: 3px;
    background: var(--dimamber);
    border-radius: 50%;
    transition: transform 0.2s, background 0.2s;
  }
  input:checked + .slider { background: #3a2000; border-color: var(--amber); }
  input:checked + .slider::before { background: var(--amber); transform: translateX(20px); }

  .controls-divider {
    width: 1px; height: 24px;
    background: var(--border);
  }

  /* capture button */
  .btn-capture {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.76rem;
    font-weight: bold;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bg);
    background: var(--amber);
    border: none;
    border-radius: 3px;
    padding: 6px 14px;
    cursor: pointer;
    transition: background 0.15s;
    flex-shrink: 0;
  }
  .btn-capture:hover   { background: #ffc840; }
  .btn-capture:active  { background: var(--dimamber); color: var(--amber); }
  .btn-capture:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    background: var(--dimamber);
    color: var(--darkamber);
  }

  /* toast */
  .toast {
    font-size: 0.7rem;
    padding: 3px 9px;
    border-radius: 3px;
    opacity: 0;
    transition: opacity 0.25s;
    pointer-events: none;
  }
  .toast.show { opacity: 1; }
  .toast.ok   { color: var(--green); background: rgba(0,255,80,0.08);  border: 1px solid rgba(0,255,80,0.2);  }
  .toast.warn { color: var(--amber); background: rgba(255,176,0,0.08); border: 1px solid rgba(255,176,0,0.2); }
  .toast.err  { color: var(--red);   background: rgba(255,50,50,0.08); border: 1px solid rgba(255,50,50,0.2); }

  /* ── Status strip ── */
  .status-strip {
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
    padding: 7px 20px;
    background: var(--darkamber);
    border-bottom: 1px solid var(--border);
    font-size: 0.72rem;
    flex-shrink: 0;
  }
  .status-strip .lbl { color: var(--dimamber); margin-right: 4px; }
  .status-strip .val { color: var(--amber); }
  .status-strip .val.red   { color: var(--red); }
  .status-strip .val.green { color: var(--green); }

  /* ── Log section ── */
  .log-section {
    flex: 1;
    overflow-y: auto;
    padding: 0 20px 24px;
  }

  .log-header {
    position: sticky;
    top: 0;
    background: var(--bg);
    font-size: 0.67rem;
    color: var(--dimamber);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 8px 0 6px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    z-index: 10;
  }

  .empty {
    padding: 40px;
    text-align: center;
    color: var(--dimwhite);
    font-size: 0.82rem;
    line-height: 1.9;
  }

  .entry {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }

  .thumb {
    flex-shrink: 0;
    width: 88px; height: 50px;
    background: var(--darkamber);
    border: 1px solid var(--border);
    border-radius: 2px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .thumb .no-thumb { font-size: 0.56rem; color: var(--dimamber); text-align: center; }

  .entry-body { flex: 1; min-width: 0; }

  .entry-meta {
    font-size: 0.66rem;
    color: var(--dimamber);
    margin-bottom: 3px;
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .tag-manual {
    color: var(--amber);
    border: 1px solid var(--dimamber);
    border-radius: 2px;
    padding: 0 3px;
    font-size: 0.6rem;
  }

  .entry-caption {
    font-size: 0.86rem;
    color: var(--white);
    line-height: 1.45;
    word-break: break-word;
  }
  .entry-caption.error { color: var(--red); font-style: italic; }
  .entry:first-child .entry-caption:not(.error) { color: var(--amber); }

  .footer-note {
    text-align: center;
    font-size: 0.66rem;
    color: var(--dimamber);
    padding: 14px 20px;
    flex-shrink: 0;
  }
</style>
</head>
<body>

<!-- Header -->
<header>
  <h1>&#9654; BearBox &mdash; Camera</h1>
  <div class="live-badge"><span>&#9679;</span> LIVE</div>
</header>

<!-- Video -->
<div class="video-section" id="video-section">
  <img src="/feed" alt="Live camera feed">
</div>

<!-- Controls -->
<div class="controls">
  <span class="controls-label">AI Capture</span>

  <div class="toggle-wrap">
    <span class="toggle-label __AUTO_LABEL_CLASS__" id="auto-label">__AUTO_LABEL_TEXT__</span>
    <label class="switch">
      <input type="checkbox" id="auto-toggle" __AUTO_CHECKED__ onchange="toggleAuto(this.checked)">
      <span class="slider"></span>
    </label>
  </div>

  <div class="controls-divider"></div>

  <button class="btn-capture" id="btn-manual" onclick="manualCapture()">
    &#9654; Capture Now
  </button>

  <span class="toast" id="toast"></span>
</div>

<!-- Status strip -->
<div class="status-strip">
  <span><span class="lbl">AI</span><span class="val" id="s-capstat">__CAP_STATUS__</span></span>
  <span><span class="lbl">MOTION</span><span class="val __MC_CLASS__" id="s-motion">__MOTION_COUNT__ events</span></span>
  <span><span class="lbl">FPS</span><span class="val" id="s-fps">__FPS__</span></span>
  <span><span class="lbl">LATEST</span><span class="val" id="s-latest" style="color:var(--dimwhite);font-size:0.68rem;">__LATEST_CAPTION__</span></span>
</div>

<!-- Log -->
<div class="log-section">
  <div class="log-header">
    <span id="log-count">Caption Log &mdash; __ENTRY_COUNT__ entries (newest first)</span>
    <span id="last-refresh">loaded __LOAD_TIME__</span>
  </div>
  <div id="log-rows">__LOG_ROWS__</div>
</div>

<p class="footer-note">
  Log refreshes every 5s &nbsp;&middot;&nbsp;
  <a href="/log" style="color:var(--dimamber);text-decoration:none;">JSON</a> &nbsp;&middot;&nbsp;
  <a href="/status" style="color:var(--dimamber);text-decoration:none;">status</a>
</p>

<script>
  // ── Toast ─────────────────────────────────────────────────
  let _toastTimer = null;
  function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className   = 'toast show ' + type;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => t.className = 'toast', 2800);
  }

  // ── Auto toggle ───────────────────────────────────────────
  function toggleAuto(checked) {
    const label = document.getElementById('auto-label');
    label.textContent = checked ? 'AUTO ON' : 'AUTO OFF';
    label.className   = 'toggle-label ' + (checked ? 'on' : 'off');

    fetch('/capture/auto', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({enabled: checked})
    })
    .then(r => r.json())
    .then(d => showToast(d.auto_enabled ? 'Auto capture ON' : 'Auto capture OFF',
                         d.auto_enabled ? 'ok' : 'warn'))
    .catch(() => showToast('Toggle failed', 'err'));
  }

  // ── Manual capture ────────────────────────────────────────
  let _captureCooldown = false;

  function manualCapture() {
    if (_captureCooldown) { showToast('Cooldown active — wait', 'warn'); return; }

    const btn = document.getElementById('btn-manual');
    btn.disabled    = true;
    btn.textContent = '⏳ Capturing...';

    fetch('/capture/now', { method: 'POST' })
      .then(r => r.json())
      .then(() => {
        showToast('Capture queued — processing...', 'ok');
        _captureCooldown = true;
        setTimeout(() => {
          _captureCooldown    = false;
          btn.disabled        = false;
          btn.textContent     = '▶ Capture Now';
        }, 15000);
      })
      .catch(() => {
        showToast('Capture failed', 'err');
        btn.disabled    = false;
        btn.textContent = '▶ Capture Now';
      });
  }

  // ── Status refresh (every 3s) ─────────────────────────────
  function refreshStatus() {
    fetch('/status')
      .then(r => r.json())
      .then(s => {
        // caption status
        const cs = document.getElementById('s-capstat');
        if (cs) cs.textContent = s.caption_status || 'IDLE';

        // FPS
        const fps = document.getElementById('s-fps');
        if (fps) fps.textContent = s.fps;

        // motion count
        const mc = document.getElementById('s-motion');
        if (mc) {
          mc.textContent = s.motion_count + ' events';
          mc.className   = 'val ' + (s.motion_count > 0 ? 'red' : '');
        }

        // latest caption preview (truncated)
        const lc = document.getElementById('s-latest');
        if (lc && s.latest_caption) {
          const txt = s.latest_caption.replace('[manual] ', '');
          lc.textContent = txt.length > 60 ? txt.slice(0, 57) + '...' : txt;
        }

        // motion border flash on video
        const vs = document.getElementById('video-section');
        if (vs) {
          if (s.motion) vs.classList.add('motion-active');
          else          vs.classList.remove('motion-active');
        }

        // sync toggle if server state diverged
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

  // ── Log refresh (every 5s) ────────────────────────────────
  function refreshLog() {
    fetch('/log')
      .then(r => r.json())
      .then(entries => {
        document.getElementById('last-refresh').textContent =
          'refreshed ' + new Date().toLocaleTimeString();
        document.getElementById('log-count').textContent =
          'Caption Log \u2014 ' + entries.length + ' entries (newest first)';

        const container = document.getElementById('log-rows');
        if (entries.length === 0) {
          container.innerHTML =
            '<div class="empty">No captions yet.<br>Waiting for motion or manual capture...</div>';
          return;
        }

        container.innerHTML = entries.map((e, i) => {
          const isManual = e.caption.startsWith('[manual]');
          const isError  = e.caption.startsWith('[error') || e.caption.startsWith('[model');
          const capText  = isManual ? e.caption.replace('[manual] ', '') : e.caption;
          const capClass = isError ? 'entry-caption error' : 'entry-caption';
          const tag      = isManual ? '<span class="tag-manual">MANUAL</span>' : '';
          const thumb    = e.thumb_b64
            ? '<img src="data:image/jpeg;base64,' + e.thumb_b64 + '" alt="frame">'
            : '<div class="no-thumb">no<br>frame</div>';

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
      .catch(() => {});
  }

  setInterval(refreshStatus, 3000);
  setInterval(refreshLog,    5000);
</script>

</body>
</html>
"""


def _fmt_ts(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _render_page_html():
    s       = _state.get_status()
    entries = _log.get_all()

    if not entries:
        rows_html = '<div class="empty">No captions yet.<br>Waiting for motion or manual capture...</div>'
    else:
        rows = []
        for e in entries:
            is_manual = e["caption"].startswith("[manual]")
            is_err    = e["caption"].startswith("[error") or e["caption"].startswith("[model")
            cap_text  = e["caption"].replace("[manual] ", "") if is_manual else e["caption"]
            cap_cls   = "entry-caption error" if is_err else "entry-caption"
            tag       = '<span class="tag-manual">MANUAL</span>' if is_manual else ""
            thumb_html = (
                f'<img src="data:image/jpeg;base64,{e["thumb_b64"]}" alt="frame">'
                if e["thumb_b64"] else '<div class="no-thumb">no<br>frame</div>'
            )
            rows.append(
                f'<div class="entry">'
                f'<div class="thumb">{thumb_html}</div>'
                f'<div class="entry-body">'
                f'<div class="entry-meta">{_fmt_ts(e["timestamp"])}{tag}</div>'
                f'<div class="{cap_cls}">{cap_text}</div>'
                f'</div></div>'
            )
        rows_html = "\n".join(rows)

    mc         = s.get("motion_count", 0)
    mc_class   = "val red" if mc > 0 else "val"
    latest_cap = s.get("latest_caption") or "none yet"
    if latest_cap and len(latest_cap) > 60:
        latest_cap = latest_cap[:57] + "..."

    html = _PAGE_HTML
    html = html.replace("__CAP_STATUS__",     s.get("caption_status", "IDLE"))
    html = html.replace("__MOTION_COUNT__",   str(mc))
    html = html.replace("__MC_CLASS__",       mc_class)
    html = html.replace("__FPS__",            str(s.get("fps", 0.0)))
    html = html.replace("__ENTRY_COUNT__",    str(len(entries)))
    html = html.replace("__LOG_ROWS__",       rows_html)
    html = html.replace("__LOAD_TIME__",      datetime.datetime.now().strftime("%H:%M:%S"))
    html = html.replace("__LATEST_CAPTION__", latest_cap)
    html = html.replace("__AUTO_ENABLED_JS__",  "true" if _caption_mod.auto_enabled else "false")
    html = html.replace("__AUTO_LABEL_CLASS__", "on" if _caption_mod.auto_enabled else "off")
    html = html.replace("__AUTO_LABEL_TEXT__",  "AUTO ON" if _caption_mod.auto_enabled else "AUTO OFF")
    html = html.replace("__AUTO_CHECKED__",     "checked" if _caption_mod.auto_enabled else "")
    return html


@app.route("/")
@app.route("/stream")
def main_ui():
    return Response(_render_page_html(), mimetype="text/html")


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
    print(f"[stream] UI at http://<ip>:{port}/stream")
    return t