# Bearbox

Plug in a USB device, it does something. Unplug it, goes back to idle. That's it.

Runs on a Raspberry Pi with a small touchscreen. Everything is Python, display draws straight to the framebuffer. No X11, no desktop.

## Quick Start

```bash
git clone https://github.com/BruBread/Bearbox
cd Bearbox
sudo bash install.sh
```

Edit `config.json` with your networks:

```json
{
  "hotspot_ssid": "yournetwork",
  "hotspot_password": "yourpassword",
  "saved_networks": {
    "home": "password",
    "phone hotspot": "password"
  }
}
```

Reboot. Plug something in.

---

## What happens when you plug stuff in

| device | what it does |
|---|---|
| USB camera | motion detection, MJPEG stream to your browser |
| USB keyboard | full shell terminal on the LCD |
| TP-Link TL-WN722N | wifi recon + pentest dashboard (web portal, port 8080) |
| TL-WN722N + ethernet | wifi-to-ethernet hotspot, routes clients out through eth0 |
| rubber ducky | runs HID payloads |
| USB drive | boots into Doom |
| nothing | clock, update checker, robot eyes |

Detection is by USB VID:PID, except keyboards (detected via `/proc/bus/input/devices`) and USB drives (detected via `lsblk`).

## Pentest mode

Triggered by a TL-WN722N adapter. Drives [bettercap](https://www.bettercap.org/) through its REST API for wifi recon, deauth, and handshake capture. Everything is controlled from a web dashboard served on the device itself — the LCD just shows connection status.

Dashboard covers:
- live AP/client recon
- deauth (channel-locked, not blind)
- handshake capture to `.pcap`
- traffic view (SSE)
- loot manager for captured files

**For authorized testing and CTFs only.** Don't point this at networks you don't own or don't have explicit permission to test. Unauthorized wifi attacks are illegal in most places.

## When there's no internet

Spins up its own network, `BearBox-AP`. Connect to it, go to `bearbox.local` in a browser, pick a saved network or type in a new one. Comes back online on its own once connected.

## Idle screens

Tap to cycle:
- clock, with CPU/RAM/disk/temp
- update checker, pulls latest commit on tap
- robot eyes, does nothing useful

## SSH commands

```bash
bbupdate     # pull latest from github, restart, show animation on screen
bbwifi       # connect to wifi
bbsave       # save a network
bbnetwork    # current ssid, ip, internet yes/no
bboffline    # force offline mode for testing
bbpentest    # pentest mode status: bettercap, portal, loot size
bblogs       # live logs
bbhelp       # everything else
```

## Stack

Python, Pillow, OpenCV, Flask, bettercap, nmcli, hostapd, dnsmasq, systemd, lgpio.

---

*Built solo, with AI assistance on boilerplate. Bugs are mine.*
