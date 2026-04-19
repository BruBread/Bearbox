#!/bin/bash
# ============================================================
#  PiAccess — Network Watcher
#  Runs as a systemd service (pa-netwatcher.service).
#  Checks every 10s if client mode is still connected.
#  If not, brings the AP back up automatically.
# ============================================================

STATE_FILE="/root/.piaccess/ap_state"
HOSTAPD_CONF="/root/.piaccess/hostapd.conf"
DNSMASQ_CONF="/root/.piaccess/dnsmasq.conf"
SAVED_NETWORKS="/root/.piaccess/saved_networks"
CONNECTING_LOCK="/tmp/pa_connecting"
CHECK_INTERVAL=10  # seconds between checks

log() { echo "[$(date '+%H:%M:%S')] netwatcher: $1"; }

start_ap() {
    source "$STATE_FILE"
    log "Starting AP: ${AP_SSID}"

    pkill hostapd        2>/dev/null || true
    pkill dnsmasq        2>/dev/null || true
    pkill wpa_supplicant 2>/dev/null || true
    sleep 1

    ip link set "$AP_IFACE" up
    ip addr flush dev "$AP_IFACE"
    ip addr add "$AP_IP/24" dev "$AP_IFACE"
    echo 1 > /proc/sys/net/ipv4/ip_forward

    if hostapd "$HOSTAPD_CONF" -B 2>/dev/null; then
        sleep 1
        dnsmasq --conf-file="$DNSMASQ_CONF" 2>/dev/null
        # Update mode in state file
        sed -i "s/^PA_MODE=.*/PA_MODE=ap/" "$STATE_FILE" 2>/dev/null || true
        log "AP is live"
    else
        log "ERROR: hostapd failed to start"
    fi
}

is_client_connected() {
    SSID=$(iwgetid -r 2>/dev/null)
    [ -n "$SSID" ]
}

ap_is_running() {
    pgrep hostapd > /dev/null 2>&1
}

try_saved_networks() {
    [ -f "$SAVED_NETWORKS" ] || return 1

    log "Scanning for saved networks..."
    nmcli device wifi rescan 2>/dev/null
    sleep 1

    local AVAILABLE
    AVAILABLE=$(nmcli -t -f SSID device wifi list 2>/dev/null)

    while IFS=$'\t' read -r SSID PASS; do
        [ -z "$SSID" ] && continue
        if echo "$AVAILABLE" | grep -qF "$SSID"; then
            log "Found saved network: ${SSID} — connecting..."
            touch "$CONNECTING_LOCK"
            if [ -n "$PASS" ]; then
                nmcli device wifi connect "$SSID" password "$PASS" ifname wlan0 2>/dev/null
            else
                nmcli device wifi connect "$SSID" ifname wlan0 2>/dev/null
            fi
            local DEADLINE=$(($(date +%s) + 20))
            while [ "$(date +%s)" -lt "$DEADLINE" ]; do
                sleep 0.5
                local CONNECTED
                CONNECTED=$(iwgetid -r 2>/dev/null)
                if [ "$CONNECTED" = "$SSID" ]; then
                    sed -i "s/^PA_MODE=.*/PA_MODE=client/" "$STATE_FILE" 2>/dev/null || true
                    rm -f "$CONNECTING_LOCK"
                    log "Connected to ${SSID}"
                    return 0
                fi
            done
            nmcli device disconnect wlan0 2>/dev/null || true
            rm -f "$CONNECTING_LOCK"
        fi
    done < "$SAVED_NETWORKS"

    return 1
}

# ── Main loop ─────────────────────────────────────────────────
log "Started"

while true; do
    sleep "$CHECK_INTERVAL"

    # If AP is already running, nothing to do
    if ap_is_running; then
        continue
    fi

    # piconnect is actively trying to connect — do not interfere
    if [ -f "$CONNECTING_LOCK" ]; then
        continue
    fi

    # AP is not running — we're in client mode
    # Check if still connected
    if ! is_client_connected; then
        log "Connection lost — trying saved networks..."
        if ! try_saved_networks; then
            log "No saved networks found — restoring AP"
            start_ap
        fi
    fi
done
