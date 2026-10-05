# Bearbox — NEXUS build

A Raspberry Pi with a small LCD that shows the **NEXUS** booth's live ticket
sales. That's all it does. No USB profiles, no pentest, no Doom — this branch is
stripped down to one job so nothing can interfere with it.

Runs on the framebuffer (no X11). Everything is Python.

## What it shows

- **Tickets** — `SOLD n / TICKETS`, read live from the booth's signup PC.
- **Eyes** — the cyan robot eyes. Tap the screen to toggle between the two.
- **Red clock** — the disconnect screen. Shown whenever there's no live ticket
  data (no Wi-Fi, no hub, or the signup server is down).

## How it finds the numbers

1. Connects to the booth Wi-Fi: `NexusV`, then `walawifi`.
2. Scans the local `/24` for the NEXUS hub (`:3000/ping` → `nexus-hub`).
3. Says hello to the hub as `bearbox`, so the GM panel's **BEARBOX** light goes
   green. The hub replies with the signup PC's address.
4. Polls `http://<signup>:4000/api/state` for the ticket count.

## Update

```
# on your machine: push to the nexus branch
git push origin nexus

# on the Pi
bbnexus        # fetch + checkout -f nexus + restart
```

First time, when the Pi is still on `main`:

```bash
cd ~/bearbox
git fetch origin
git checkout -f -B nexus origin/nexus
sudo bash bbcommands/install_bbcommands.sh
sudo systemctl restart bearbox
```

## Commands

`bbhelp` lists them. Service control (`bbstart`/`bbstop`/`bbrestart`/`bbstatus`/
`bblogs`), `bbnexus` to update, `bbnetwork`/`bbip` for Wi-Fi status, `bbscreen
bear|nexus` to run a screen by hand.

## Stack

Python, Pillow, numpy, websocket-client, systemd.
