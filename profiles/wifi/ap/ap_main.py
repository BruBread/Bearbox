#!/usr/bin/env python3
"""
BearBox AP — Main Entry Point
Sets up AP and runs Siphon UI.
"""

import os
import sys
import time
import subprocess
import signal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.."))
from display import new_frame, push, font, W, H
from profiles.wifi.ap.ap_utils import C, fonts, draw_header, draw_scanlines_pink, run_cmd

AP_IFACE   = "wlan0"
ETH_IFACE  = "eth0"
AP_IP      = "10.0.0.1"
DHCP_START = "10.0.0.10"
DHCP_END   = "10.0.0.50"

def _load_config():
    import json
    path = os.path.join(os.path.dirname(__file__), "../../../config.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def _show_status(msg, color=None):
    F   = fonts()
    col = color or C["pink"]
    img, d = new_frame(bg=C["bg"])
    draw_scanlines_pink(d)
    draw_header(d, F, "SIPHON", "initializing...")
    mw = F["body"].getbbox(msg)[2]
    d.text(((W-mw)//2, H//2-10), msg, font=F["body"], fill=col)
    push(img)

def setup_ap():
    cfg     = _load_config()
    ap_ssid = cfg.get("ap_ssid",    "BearBox-AP")
    ap_pass = cfg.get("ap_password", "Bearbox123")

    _show_status("Configuring AP...")
    run_cmd(f"nmcli device set {AP_IFACE} managed no 2>/dev/null")
    run_cmd("sudo pkill hostapd 2>/dev/null")
    run_cmd("sudo pkill dnsmasq 2>/dev/null")
    time.sleep(1)

    run_cmd(f"sudo ip link set {AP_IFACE} up")
    run_cmd(f"sudo ip addr flush dev {AP_IFACE}")
    run_cmd(f"sudo ip addr add {AP_IP}/24 dev {AP_IFACE}")

    with open("/tmp/bb_hostapd.conf", "w") as f:
        f.write(f"""interface={AP_IFACE}
driver=nl80211
ssid={ap_ssid}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={ap_pass}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
""")

    with open("/tmp/bb_dnsmasq.conf", "w") as f:
        f.write(f"""interface={AP_IFACE}
dhcp-range={DHCP_START},{DHCP_END},255.255.255.0,24h
dhcp-option=3,{AP_IP}
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
""")

    _show_status("Starting hostapd...")
    r = subprocess.run("sudo hostapd /tmp/bb_hostapd.conf -B",
                       shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        _show_status("hostapd failed!", color=C["red"])
        time.sleep(2)
        return False

    _show_status("Starting dnsmasq...")
    run_cmd("sudo dnsmasq --conf-file=/tmp/bb_dnsmasq.conf")

    _show_status("Enabling routing...")
    run_cmd("echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward > /dev/null")
    run_cmd(f"sudo iptables -A FORWARD -i {AP_IFACE} -o {ETH_IFACE} -j ACCEPT")
    run_cmd(f"sudo iptables -A FORWARD -i {ETH_IFACE} -o {AP_IFACE} "
            f"-m state --state RELATED,ESTABLISHED -j ACCEPT")
    run_cmd(f"sudo iptables -t nat -A POSTROUTING -o {ETH_IFACE} -j MASQUERADE")
    return True

def teardown_ap():
    run_cmd("sudo pkill hostapd 2>/dev/null")
    run_cmd("sudo pkill dnsmasq 2>/dev/null")
    run_cmd(f"sudo iptables -D FORWARD -i {AP_IFACE} -o {ETH_IFACE} -j ACCEPT 2>/dev/null")
    run_cmd(f"sudo iptables -D FORWARD -i {ETH_IFACE} -o {AP_IFACE} "
            f"-m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null")
    run_cmd(f"sudo iptables -t nat -D POSTROUTING -o {ETH_IFACE} -j MASQUERADE 2>/dev/null")
    run_cmd(f"sudo ip addr flush dev {AP_IFACE} 2>/dev/null")
    run_cmd(f"nmcli device set {AP_IFACE} managed yes 2>/dev/null")

def run():
    signal.signal(signal.SIGTERM, lambda s, f: (teardown_ap(), sys.exit(0)))
    try:
        if not setup_ap():
            return
        from profiles.wifi.ap.ap_intro     import run as play_intro
        from profiles.wifi.ap.ap_dashboard import run as show_dashboard
        play_intro()
        show_dashboard()
    finally:
        teardown_ap()

if __name__ == "__main__":
    run()
