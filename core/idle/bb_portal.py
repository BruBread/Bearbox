#!/usr/bin/env python3
"""
BearBox WiFi Portal — bb_portal.py

Runs as a background thread when offline mode starts.
Serves on port 80 at bearbox.local (resolved by dnsmasq).

Endpoints:
  GET  /           — main page (saved networks + scan for new)
  GET  /scan       — returns JSON list of visible SSIDs
  POST /connect    — connect to a network {ssid, password}
  GET  /status     — returns JSON connection status (polled by page)
"""

import os
import sys
import json
import time
import threading
import subprocess

from flask import Flask, request, jsonify, render_template_string

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CONFIG_PATH = "/home/bearbox/bearbox/config.json"
IFACE       = "wlan0"
AP_IP       = "10.0.0.1"

app = Flask(__name__)

# ── shared state ──────────────────────────────────────────────
_status = {
    "state":   "idle",   # idle | connecting | connected | failed
    "ssid":    "",
    "message": "",
}
_status_lock = threading.Lock()

def _set_status(state, ssid="", message=""):
    with _status_lock:
        _status["state"]   = state
        _status["ssid"]    = ssid
        _status["message"] = message

# ── helpers ───────────────────────────────────────────────────

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def _load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def _load_saved_networks():
    cfg      = _load_config()
    networks = dict(cfg.get("saved_networks", {}))
    ssid     = cfg.get("hotspot_ssid", "")
    pw       = cfg.get("hotspot_password", "")
    if ssid and ssid not in networks:
        networks[ssid] = pw
    return networks

def _teardown_ap():
    _run("sudo pkill hostapd 2>/dev/null")
    _run("sudo pkill dnsmasq 2>/dev/null")
    _run(f"sudo ip addr flush dev {IFACE} 2>/dev/null")
    _run(f"sudo nmcli device set {IFACE} managed yes 2>/dev/null")
    time.sleep(0.5)

def _restore_ap():
    _run(f"sudo nmcli device set {IFACE} managed no 2>/dev/null")
    _run(f"sudo ip link set {IFACE} up")
    _run(f"sudo ip addr add {AP_IP}/24 dev {IFACE} 2>/dev/null")
    with open("/tmp/bb_offline_hostapd.conf", "w") as f:
        f.write(f"interface={IFACE}\ndriver=nl80211\nssid=BearBox-AP\n"
                f"hw_mode=g\nchannel=6\nwmm_enabled=0\nmacaddr_acl=0\n"
                f"auth_algs=1\nignore_broadcast_ssid=0\nwpa=2\n"
                f"wpa_passphrase=Bearbox123\nwpa_key_mgmt=WPA-PSK\n"
                f"wpa_pairwise=TKIP\nrsn_pairwise=CCMP\n")
    with open("/tmp/bb_offline_dnsmasq.conf", "w") as f:
        f.write(f"interface={IFACE}\n"
                f"dhcp-range=10.0.0.10,10.0.0.50,255.255.255.0,24h\n"
                f"dhcp-option=3,{AP_IP}\ndhcp-option=6,8.8.8.8\n"
                f"address=/bearbox.local/{AP_IP}\n")
    _run("sudo hostapd /tmp/bb_offline_hostapd.conf -B 2>/dev/null")
    time.sleep(1)
    _run("sudo dnsmasq --conf-file=/tmp/bb_offline_dnsmasq.conf 2>/dev/null")

def _do_connect(ssid, password):
    """Runs in a thread. Tears down AP, tries to connect, restores AP on fail."""
    _set_status("connecting", ssid, f"Connecting to {ssid}...")
    _teardown_ap()

    psk_line = f'psk="{password}"' if password else "key_mgmt=NONE"
    wpa = (f"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n"
           f"update_config=1\nnetwork={{\n"
           f"    ssid=\"{ssid}\"\n    {psk_line}\n    priority=10\n}}\n")
    with open("/tmp/bb_saved.conf", "w") as f:
        f.write(wpa)

    _run("sudo pkill wpa_supplicant 2>/dev/null")
    time.sleep(0.5)
    _run(f"sudo ip link set {IFACE} up")
    _run(f"sudo wpa_supplicant -B -i {IFACE} -c /tmp/bb_saved.conf 2>/dev/null")

    # Poll for association
    deadline = time.time() + 12
    while time.time() < deadline:
        if _run("iwgetid -r 2>/dev/null"):
            break
        time.sleep(0.5)

    # Request DHCP
    _run(f"sudo dhcpcd {IFACE} 2>/dev/null || sudo dhclient {IFACE} 2>/dev/null")

    # Poll for IP + internet
    deadline2 = time.time() + 6
    while time.time() < deadline2:
        result = _run(f"ip -4 addr show {IFACE}")
        if "inet " in result:
            r = subprocess.run("ping -c 1 -W 2 8.8.8.8",
                               shell=True, capture_output=True)
            if r.returncode == 0:
                # Save to config if it's a new network
                if password is not None:
                    cfg = _load_config()
                    if "saved_networks" not in cfg:
                        cfg["saved_networks"] = {}
                    cfg["saved_networks"][ssid] = password
                    _save_config(cfg)
                _set_status("connected", ssid, f"Connected to {ssid}!")
                # Restart bearbox service to come back online
                time.sleep(1.5)
                subprocess.Popen(["sudo", "systemctl", "restart", "bearbox"])
                return
        time.sleep(0.5)

    # Failed
    _run("sudo pkill wpa_supplicant 2>/dev/null")
    _restore_ap()
    _set_status("failed", ssid, f"Could not connect to {ssid}")

# ── HTML page ─────────────────────────────────────────────────
PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="theme-color" content="#0c0000">
<title>BearBox</title>
<style>
  :root {
    --bg:       #0c0000;
    --panel:    #160000;
    --border:   #3a0000;
    --red:      #ff2828;
    --midred:   #b41414;
    --dimred:   #460000;
    --white:    #ffdcdc;
    --dimwhite: #8c5050;
    --green:    #28ff28;
    --amber:    #ff8c00;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--white);
    font-family: 'Courier New', monospace;
    min-height: 100vh;
    padding: 0 0 40px 0;
  }
  /* scanlines overlay */
  body::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 3px,
      rgba(0,0,0,0.18) 3px,
      rgba(0,0,0,0.18) 4px
    );
    pointer-events: none;
    z-index: 999;
  }
  header {
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    padding: 18px 20px 14px;
    text-align: center;
  }
  header h1 {
    font-size: 22px;
    font-weight: bold;
    letter-spacing: 4px;
    color: var(--red);
    text-shadow: 0 0 12px rgba(255,40,40,0.4);
  }
  header p {
    font-size: 11px;
    color: var(--dimwhite);
    margin-top: 4px;
    letter-spacing: 1px;
  }
  .section {
    margin: 18px 16px 0;
  }
  .section-title {
    font-size: 10px;
    letter-spacing: 3px;
    color: var(--midred);
    text-transform: uppercase;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--dimred);
  }
  .net-btn {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--white);
    font-family: 'Courier New', monospace;
    font-size: 14px;
    padding: 14px 16px;
    margin-bottom: 8px;
    cursor: pointer;
    text-align: left;
    transition: border-color 0.15s, background 0.15s;
    -webkit-tap-highlight-color: transparent;
  }
  .net-btn:active, .net-btn.pressed {
    background: #2a0000;
    border-color: var(--red);
  }
  .net-btn .ssid { font-weight: bold; }
  .net-btn .tag {
    font-size: 10px;
    color: var(--dimwhite);
    letter-spacing: 1px;
  }
  .net-btn .tag.saved { color: var(--midred); }

  /* password form — hidden by default */
  .pw-form {
    display: none;
    background: #100000;
    border: 1px solid var(--border);
    border-top: none;
    padding: 12px 14px;
    margin-top: -8px;
    margin-bottom: 8px;
  }
  .pw-form.open { display: block; }
  .pw-form input[type=text],
  .pw-form input[type=password] {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--midred);
    color: var(--white);
    font-family: 'Courier New', monospace;
    font-size: 14px;
    padding: 10px 12px;
    outline: none;
    margin-bottom: 8px;
  }
  .pw-form input::placeholder { color: var(--dimwhite); }
  .pw-form .row {
    display: flex;
    gap: 8px;
  }
  .btn {
    flex: 1;
    background: var(--dimred);
    border: 1px solid var(--midred);
    color: var(--white);
    font-family: 'Courier New', monospace;
    font-size: 13px;
    padding: 10px;
    cursor: pointer;
    letter-spacing: 1px;
    -webkit-tap-highlight-color: transparent;
  }
  .btn.primary {
    background: #3a0000;
    border-color: var(--red);
    color: var(--red);
    font-weight: bold;
  }
  .btn:active { opacity: 0.7; }

  /* status banner */
  #status-bar {
    display: none;
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: var(--panel);
    border-top: 1px solid var(--border);
    padding: 12px 16px;
    font-size: 12px;
    letter-spacing: 1px;
    text-align: center;
    z-index: 100;
  }
  #status-bar.show { display: block; }
  #status-bar.connecting { color: var(--amber); border-color: var(--amber); }
  #status-bar.connected  { color: var(--green); border-color: var(--green); }
  #status-bar.failed     { color: var(--red);   border-color: var(--red); }

  .spinner {
    display: inline-block;
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .scan-btn {
    width: 100%;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--dimwhite);
    font-family: 'Courier New', monospace;
    font-size: 12px;
    letter-spacing: 2px;
    padding: 12px;
    cursor: pointer;
    margin-bottom: 10px;
    -webkit-tap-highlight-color: transparent;
  }
  .scan-btn:active { border-color: var(--red); color: var(--red); }

  #scan-results { margin-top: 4px; }
  .no-networks {
    text-align: center;
    color: var(--dimwhite);
    font-size: 12px;
    padding: 20px 0;
    letter-spacing: 1px;
  }
</style>
</head>
<body>

<header>
  <h1>BEARBOX</h1>
  <p>WIFI SETUP  •  bearbox.local</p>
</header>

{% if saved %}
<div class="section">
  <div class="section-title">Saved Networks</div>
  {% for ssid in saved %}
  <button class="net-btn" onclick="connectSaved('{{ ssid }}', this)">
    <span class="ssid">{{ ssid }}</span>
    <span class="tag saved">SAVED</span>
  </button>
  {% endfor %}
</div>
{% endif %}

<div class="section">
  <div class="section-title">New Network</div>
  <button class="scan-btn" onclick="doScan(this)">▶ SCAN FOR NETWORKS</button>
  <div id="scan-results"></div>
</div>

<div id="status-bar"></div>

<script>
  let _connecting = false;

  function setStatus(state, msg) {
    const bar = document.getElementById('status-bar');
    bar.className = 'show ' + state;
    bar.innerHTML = state === 'connecting'
      ? '<span class="spinner">◐</span>  ' + msg
      : msg;
    if (state === 'connected') {
      setTimeout(() => { bar.className = ''; }, 4000);
    }
  }

  function connectSaved(ssid, btn) {
    if (_connecting) return;
    btn.classList.add('pressed');
    setTimeout(() => btn.classList.remove('pressed'), 300);
    startConnect(ssid, '');
  }

  function startConnect(ssid, password) {
    if (_connecting) return;
    _connecting = true;
    setStatus('connecting', 'Connecting to ' + ssid + '...');
    fetch('/connect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ssid: ssid, password: password})
    });
    pollStatus();
  }

  function pollStatus() {
    fetch('/status')
      .then(r => r.json())
      .then(data => {
        if (data.state === 'connecting') {
          setStatus('connecting', data.message);
          setTimeout(pollStatus, 800);
        } else if (data.state === 'connected') {
          setStatus('connected', '✓  ' + data.message);
          _connecting = false;
        } else if (data.state === 'failed') {
          setStatus('failed', '✗  ' + data.message);
          _connecting = false;
        } else {
          setTimeout(pollStatus, 800);
        }
      })
      .catch(() => setTimeout(pollStatus, 1000));
  }

  function doScan(btn) {
    if (_connecting) return;
    btn.innerHTML = '<span class="spinner">◐</span>  SCANNING...';
    btn.disabled = true;
    fetch('/scan')
      .then(r => r.json())
      .then(data => {
        btn.innerHTML = '▶ SCAN FOR NETWORKS';
        btn.disabled = false;
        renderScan(data.networks || []);
      })
      .catch(() => {
        btn.innerHTML = '▶ SCAN FOR NETWORKS';
        btn.disabled = false;
      });
  }

  function renderScan(networks) {
    const el = document.getElementById('scan-results');
    if (!networks.length) {
      el.innerHTML = '<div class="no-networks">No networks found</div>';
      return;
    }
    el.innerHTML = networks.map(n => `
      <button class="net-btn" onclick="openPwForm('${n.ssid}', ${n.secured}, this)">
        <span class="ssid">${n.ssid}</span>
        <span class="tag">${n.secured ? 'SECURED' : 'OPEN'}</span>
      </button>
      <div class="pw-form" id="form-${btoa(n.ssid).replace(/=/g,'')}">
        ${n.secured ? `<input type="password" placeholder="Password" id="pw-${btoa(n.ssid).replace(/=/g,'')}">` : ''}
        <div class="row">
          <button class="btn" onclick="closePwForm('${n.ssid}')">CANCEL</button>
          <button class="btn primary" onclick="connectNew('${n.ssid}', ${n.secured})">CONNECT</button>
        </div>
      </div>
    `).join('');
  }

  function _formId(ssid) {
    return btoa(ssid).replace(/=/g, '');
  }

  function openPwForm(ssid, secured, btn) {
    if (_connecting) return;
    // close others
    document.querySelectorAll('.pw-form.open').forEach(f => f.classList.remove('open'));
    const form = document.getElementById('form-' + _formId(ssid));
    if (!secured) {
      // open network — connect immediately
      startConnect(ssid, '');
      return;
    }
    form.classList.add('open');
    const pw = document.getElementById('pw-' + _formId(ssid));
    if (pw) setTimeout(() => pw.focus(), 100);
  }

  function closePwForm(ssid) {
    const form = document.getElementById('form-' + _formId(ssid));
    if (form) form.classList.remove('open');
  }

  function connectNew(ssid, secured) {
    let pw = '';
    if (secured) {
      const inp = document.getElementById('pw-' + _formId(ssid));
      pw = inp ? inp.value : '';
      if (!pw) { inp.focus(); return; }
    }
    closePwForm(ssid);
    startConnect(ssid, pw);
  }
</script>
</body>
</html>
"""

# ── routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    saved = list(_load_saved_networks().keys())
    return render_template_string(PAGE, saved=saved)

@app.route("/scan")
def scan():
    try:
        _run("sudo nmcli device wifi rescan 2>/dev/null")
        time.sleep(1.2)
        raw = _run("nmcli -t -f SSID,SECURITY device wifi list 2>/dev/null")
        seen = set()
        networks = []
        for line in raw.splitlines():
            parts = line.split(":")
            if not parts or not parts[0].strip():
                continue
            ssid     = parts[0].strip()
            security = parts[1].strip() if len(parts) > 1 else ""
            if ssid and ssid not in seen:
                seen.add(ssid)
                networks.append({
                    "ssid":    ssid,
                    "secured": bool(security and security != "--"),
                })
        return jsonify({"networks": networks})
    except Exception as e:
        return jsonify({"networks": [], "error": str(e)})

@app.route("/connect", methods=["POST"])
def connect():
    if _status["state"] == "connecting":
        return jsonify({"ok": False, "error": "already connecting"})
    data     = request.get_json(force=True)
    ssid     = data.get("ssid", "").strip()
    password = data.get("password", "")
    if not ssid:
        return jsonify({"ok": False, "error": "no ssid"})
    threading.Thread(target=_do_connect, args=(ssid, password), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/status")
def status():
    with _status_lock:
        return jsonify(dict(_status))

# ── public API ────────────────────────────────────────────────

_server_thread = None

def start(host="0.0.0.0", port=80):
    """Start the portal web server in a background daemon thread."""
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        return
    def _run_flask():
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    _server_thread = threading.Thread(target=_run_flask, daemon=True)
    _server_thread.start()
    print(f">> Portal running at http://bearbox.local (port {port})")


if __name__ == "__main__":
    start()
    print("Portal running — Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
