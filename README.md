# Bearbox

plug in a usb device, it does something. unplug it, goes back to idle. thats it.

built on a raspberry pi with a small touchscreen. everything is python, display is drawn straight to the framebuffer.

---

## what happens when you plug stuff in

| device | what it does |
|---|---|
| usb camera | motion detection, streams to your browser |
| usb keyboard | actual terminal with shell access |
| tp-link adapter + ethernet | turns into a wifi hotspot |
| rubber ducky | runs hid payloads |
| nothing | clock, github updater, robot eyes |

---

## when theres no internet

spins up its own wifi network called `BearBox-AP`. scan the qr code on screen, connect your phone, browser opens a page where you can connect to a saved network. comes back online by itself.

---

## idle screens

tap the screen to switch between:

- clock with cpu/ram/temp stats
- update checker — sees if theres a new commit on github, tap to pull and restart
- bear (robot eyes that move around)

---

## ssh commands
```bash
bbupdate     # pulls latest from github, restarts, shows animation on screen
bbwifi       # connect to wifi
bbsave       # save a network
bbnetwork    # current ssid, ip, internet yes/no
bboffline    # force offline mode for testing
bblogs       # live logs
bbhelp       # everything else
```

---

## setup
```bash
git clone https://github.com/BruBread/Bearbox
cd Bearbox
sudo bash install.sh
```

then edit `config.json` with your wifi networks:
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

---

## stack

python, pillow, opencv, flask, nmcli, hostapd, systemd

---

*made with ai assistance. sorry about all the tokens.*
