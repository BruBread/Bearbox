#!/bin/bash
# ============================================================
#  PiAccess — pi* Commands
#  Sourced by ~/.bashrc on every shell start.
#  Do not run directly.
#
#  Modes:
#    AP mode      — wlan0 is a hotspot, SSH via 10.0.0.1
#    Client mode  — wlan0 connected to home network, AP off
#                   netwatcher auto-recovers AP if it drops
# ============================================================

_PA_DIR="$HOME/.piaccess"
_PA_STATE="$_PA_DIR/ap_state"
_PA_HOSTAPD_CONF="$_PA_DIR/hostapd.conf"
_PA_DNSMASQ_CONF="$_PA_DIR/dnsmasq.conf"
_PA_CONNECTING_LOCK="/tmp/pa_connecting"

# ── Colors ────────────────────────────────────────────────────
_BGRN='\033[1;32m'
_BRED='\033[1;31m'
_BCYN='\033[1;36m'
_BYLW='\033[1;33m'
_BWHT='\033[1;37m'
_DIM='\033[2m'
_NC='\033[0m'

_pa_info()    { echo -e "${_BCYN}  → $1${_NC}"; }
_pa_ok()      { echo -e "${_BGRN}  ✓ $1${_NC}"; }
_pa_warn()    { echo -e "${_BYLW}  ! $1${_NC}"; }
_pa_err()     { echo -e "${_BRED}  ✗ $1${_NC}"; }

# Ensure sudo credentials are cached — prompts once if needed
_pa_sudo() {
    sudo -v 2>/dev/null || { _pa_err "sudo authentication failed"; return 1; }
}

_pa_load_state() {
    if [ -f "$_PA_STATE" ]; then
        source "$_PA_STATE"
    else
        AP_SSID="pi-$(whoami)"
        AP_PASS=""
        AP_IFACE="wlan0"
        AP_IP="10.0.0.1"
        PA_MODE="ap"
    fi
}

_pa_save_mode() {
    if [ -f "$_PA_STATE" ]; then
        if grep -q "^PA_MODE=" "$_PA_STATE"; then
            sudo sed -i "s/^PA_MODE=.*/PA_MODE=$1/" "$_PA_STATE"
        else
            echo "PA_MODE=$1" | sudo tee -a "$_PA_STATE" > /dev/null
        fi
    fi
}

# ── Internal: bring AP up ─────────────────────────────────────
_pa_start_ap() {
    _pa_load_state

    sudo pkill hostapd        2>/dev/null || true
    sudo pkill dnsmasq        2>/dev/null || true
    sudo pkill wpa_supplicant 2>/dev/null || true
    sleep 1

    sudo ip link set "$AP_IFACE" up
    sudo ip addr flush dev "$AP_IFACE"
    sudo ip addr add "$AP_IP/24" dev "$AP_IFACE"
    echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward > /dev/null

    if sudo hostapd "$_PA_HOSTAPD_CONF" -B 2>/dev/null; then
        sleep 1
        sudo dnsmasq --conf-file="$_PA_DNSMASQ_CONF" 2>/dev/null
        _pa_save_mode "ap"
        return 0
    fi
    return 1
}

# ── Internal: tear AP down ────────────────────────────────────
_pa_stop_ap() {
    sudo pkill hostapd 2>/dev/null || true
    sudo pkill dnsmasq 2>/dev/null || true
    sleep 1
    _pa_load_state
    sudo ip addr flush dev "$AP_IFACE" 2>/dev/null || true
}

# ─────────────────────────────────────────────────────────────

# ── pihelp ────────────────────────────────────────────────────
pihelp() {
    _pa_load_state
    echo ""
    echo -e "${_BWHT}  PiAccess Commands${_NC}"
    echo -e "  ${_DIM}────────────────────────────────────${_NC}"
    echo -e "  ${_BYLW}pihelp${_NC}                       Show this help"
    echo -e "  ${_BYLW}pistatus${_NC}                     Current mode, IPs, connected clients"
    echo -e "  ${_BYLW}piap${_NC}                         Switch back to AP mode"
    echo -e "  ${_BYLW}pilock [password]${_NC}            Add a password to the AP"
    echo -e "  ${_BYLW}piunlock${_NC}                     Remove AP password (open network)"
    echo -e "  ${_BYLW}piwifi${_NC}                       Scan and connect to a Wi-Fi network"
    echo -e "  ${_BYLW}piconnect <ssid> [password]${_NC}  Connect to a specific network"
    echo -e "  ${_BYLW}pisaved${_NC}                      View and remove saved networks"
    echo -e "  ${_BYLW}piadd [ssid] [password]${_NC}      Add a network to auto-connect list"
    echo -e "  ${_BYLW}piupdate${_NC}                     Check for and install SSHit updates"
    echo -e "  ${_BYLW}pirestart${_NC}                    Reboot the Pi"
    echo -e "  ${_DIM}────────────────────────────────────${_NC}"
    echo -e "  ${_DIM}AP mode:     Pi broadcasts ${_BYLW}${AP_SSID:-pi-USERNAME}${_DIM}, SSH to 10.0.0.1${_NC}"
    echo -e "  ${_DIM}Client mode: Pi joins your network, AP off${_NC}"
    echo -e "  ${_DIM}             Watcher auto-restores AP if connection drops${_NC}"
    echo ""
}

# ── pistatus ──────────────────────────────────────────────────
pistatus() {
    _pa_load_state

    echo ""
    echo -e "${_BWHT}  PiAccess Status${_NC}"
    echo -e "  ${_DIM}────────────────────────────────────${_NC}"

    if pgrep hostapd > /dev/null 2>&1; then
        echo -e "  Mode:      ${_BGRN}AP${_NC}"
        if [ -z "$AP_PASS" ]; then
            echo -e "  SSID:      ${_BYLW}${AP_SSID}${_NC}  ${_DIM}(open)${_NC}"
        else
            echo -e "  SSID:      ${_BYLW}${AP_SSID}${_NC}  ${_DIM}(password protected)${_NC}"
        fi
        echo -e "  SSH via:   ${_BYLW}ssh $(whoami)@${AP_IP}${_NC}"
        echo ""

        LEASE_FILE="/var/lib/misc/dnsmasq.leases"
        if [ -f "$LEASE_FILE" ] && [ -s "$LEASE_FILE" ]; then
            COUNT=$(wc -l < "$LEASE_FILE")
            echo -e "  Clients:   ${_BYLW}${COUNT}${_NC} connected"
            while IFS= read -r line; do
                IP=$(echo   "$line" | awk '{print $3}')
                HOST=$(echo "$line" | awk '{print $4}')
                MAC=$(echo  "$line" | awk '{print $2}')
                [ "$HOST" = "*" ] && HOST="Unknown"
                echo -e "    ${_BCYN}${IP}${_NC}  ${HOST}  ${_DIM}${MAC}${_NC}"
            done < "$LEASE_FILE"
        else
            echo -e "  Clients:   ${_DIM}none${_NC}"
        fi
    else
        echo -e "  Mode:      ${_BCYN}CLIENT${_NC}"
        CURRENT_SSID=$(iwgetid -r 2>/dev/null)
        if [ -n "$CURRENT_SSID" ]; then
            echo -e "  Network:   ${_BGRN}${CURRENT_SSID}${_NC}"
            HOME_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | \
                      grep -v "^${AP_IP}" | grep -v "^$" | head -1)
            [ -n "$HOME_IP" ] && echo -e "  IP:        ${_BYLW}${HOME_IP}${_NC}"
        else
            echo -e "  Network:   ${_BRED}disconnected${_NC}  ${_DIM}(watcher will restore AP)${_NC}"
        fi
    fi

    echo ""
    if ping -c 1 -W 2 8.8.8.8 > /dev/null 2>&1; then
        echo -e "  Internet:  ${_BGRN}reachable${_NC}"
    else
        echo -e "  Internet:  ${_BRED}not reachable${_NC}"
    fi

    echo ""
    if systemctl is-active --quiet pa-netwatcher 2>/dev/null; then
        echo -e "  Watcher:   ${_BGRN}running${_NC}  ${_DIM}(auto-recovers AP on disconnect)${_NC}"
    else
        echo -e "  Watcher:   ${_BRED}stopped${_NC}  ${_DIM}(sudo systemctl start pa-netwatcher)${_NC}"
    fi

    echo -e "  ${_DIM}────────────────────────────────────${_NC}"
    echo ""
}

# ── piap ──────────────────────────────────────────────────────
piap() {
    _pa_sudo || return 1
    _pa_load_state

    echo ""
    _pa_info "Switching to AP mode: ${AP_SSID}..."

    if _pa_start_ap; then
        _pa_ok "AP is live — ${_BYLW}${AP_SSID}${_BGRN} → SSH to ${_BYLW}${AP_IP}"
    else
        _pa_err "hostapd failed to start"
        _pa_warn "Check: sudo journalctl -u hostapd --no-pager -n 20"
    fi
    echo ""
}

# ── pilock ────────────────────────────────────────────────────
pilock() {
    _pa_sudo || return 1
    _pa_load_state

    local PASSWORD="$1"

    if [ -z "$PASSWORD" ]; then
        echo ""
        echo -e "${_BWHT}  Lock AP with a password${_NC}"
        read -rsp "  Enter password (8+ chars): " PASSWORD
        echo ""
        if [ ${#PASSWORD} -lt 8 ]; then
            _pa_err "Password must be at least 8 characters"
            return 1
        fi
        read -rsp "  Confirm password: " PASSWORD2
        echo ""
        if [ "$PASSWORD" != "$PASSWORD2" ]; then
            _pa_err "Passwords don't match"
            return 1
        fi
    fi

    if [ ${#PASSWORD} -lt 8 ]; then
        _pa_err "Password must be at least 8 characters (WPA2 requirement)"
        return 1
    fi

    _pa_info "Setting AP password..."

    sudo tee "$_PA_HOSTAPD_CONF" > /dev/null << EOF
interface=${AP_IFACE}
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${PASSWORD}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

    sudo sed -i "s/^AP_PASS=.*/AP_PASS=${PASSWORD}/" "$_PA_STATE"
    piap
    _pa_ok "AP is now password protected"
    echo -e "  Password: ${_BYLW}${PASSWORD}${_NC}"
    echo ""
}

# ── piunlock ──────────────────────────────────────────────────
piunlock() {
    _pa_sudo || return 1
    _pa_load_state

    _pa_info "Removing AP password..."

    sudo tee "$_PA_HOSTAPD_CONF" > /dev/null << EOF
interface=${AP_IFACE}
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
EOF

    sudo sed -i "s/^AP_PASS=.*/AP_PASS=/" "$_PA_STATE"
    piap
    _pa_ok "AP is now open (no password)"
    echo ""
}

# ── piwifi ────────────────────────────────────────────────────
piwifi() {
    _pa_sudo || return 1

    echo ""
    echo -e "  ${_BYLW}⚠️  WARNING:${_NC} The AP must shut down to scan for networks."
    echo -e "  ${_DIM}Your SSH session will disconnect briefly. This is normal.${_NC}"
    echo -e "  ${_DIM}If you cancel or no network is chosen, AP will come back up.${_NC}"
    echo ""
    read -rp "$(echo -e "  ${_BWHT}Continue? (y/n):${_NC} ")" proceed
    if [ "$proceed" != "y" ]; then
        _pa_warn "Cancelled."
        echo ""
        return 0
    fi
    _pa_info "Turning off AP to scan..."
    _pa_stop_ap

    NETWORKS=$(sudo iwlist wlan0 scan 2>/dev/null | \
        grep 'ESSID:' | \
        sed 's/.*ESSID:"//;s/".*//' | \
        grep -v "^$" | \
        sort -u)

    if [ -z "$NETWORKS" ]; then
        _pa_warn "No networks found — restarting AP"
        _pa_start_ap
        return 1
    fi

    echo ""
    echo -e "${_BWHT}  Available Networks:${_NC}"
    echo -e "  ${_DIM}────────────────────────────────────${_NC}"

    i=1
    declare -A NET_MAP
    while IFS= read -r ssid; do
        echo -e "  ${_BYLW}${i})${_NC} ${ssid}"
        NET_MAP[$i]="$ssid"
        ((i++))
    done <<< "$NETWORKS"

    echo -e "  ${_DIM}────────────────────────────────────${_NC}"
    echo ""
    read -rp "  Enter number to connect (or q to go back to AP): " CHOICE

    if [ "$CHOICE" = "q" ]; then
        _pa_info "Restarting AP..."
        _pa_start_ap && _pa_ok "AP is back up: ${_BYLW}${AP_SSID}"
        echo ""
        return 0
    fi

    CHOSEN_SSID="${NET_MAP[$CHOICE]}"
    if [ -z "$CHOSEN_SSID" ]; then
        _pa_err "Invalid choice — restarting AP"
        _pa_start_ap
        return 1
    fi

    read -rsp "  Password for '${CHOSEN_SSID}' (leave blank if open): " WIFI_PASS
    echo ""

    piconnect "$CHOSEN_SSID" "$WIFI_PASS"
}

# ── Saved networks (JSON-less, stored in ap_state) ────────────
_pa_save_network() {
    local SSID="$1"
    local PASS="$2"
    local SAVED_FILE="$_PA_DIR/saved_networks"
    # Format: one per line  SSID<TAB>PASS  (PASS may be empty)
    sudo touch "$SAVED_FILE"
    # Remove existing entry for this SSID then append
    sudo sed -i "/^${SSID}\t/d" "$SAVED_FILE" 2>/dev/null || true
    printf '%s\t%s\n' "$SSID" "$PASS" | sudo tee -a "$SAVED_FILE" > /dev/null
}

_pa_try_saved_networks() {
    local SAVED_FILE="$_PA_DIR/saved_networks"
    [ -f "$SAVED_FILE" ] || return 1

    _pa_info "Scanning for saved networks..."
    sudo nmcli device wifi rescan 2>/dev/null
    sleep 1

    local AVAILABLE
    AVAILABLE=$(sudo nmcli -t -f SSID device wifi list 2>/dev/null | grep -v '^$')

    while IFS=$'\t' read -r SSID PASS; do
        [ -z "$SSID" ] && continue
        if echo "$AVAILABLE" | grep -qF "$SSID"; then
            _pa_info "Found saved network: ${SSID} — connecting..."
            _pa_nmcli_connect "$SSID" "$PASS" && return 0
        fi
    done < "$SAVED_FILE"

    return 1
}

# ── Internal: connect via nmcli (like bearbox) ────────────────
_pa_nmcli_connect() {
    local SSID="$1"
    local PASS="$2"

    # Remove stale nmcli profile to avoid conflicts
    sudo nmcli connection delete "$SSID" 2>/dev/null || true

    if [ -n "$PASS" ]; then
        sudo nmcli device wifi connect "$SSID" password "$PASS" ifname wlan0 2>/dev/null &
    else
        sudo nmcli device wifi connect "$SSID" ifname wlan0 2>/dev/null &
    fi

    local DEADLINE=$(($(date +%s) + 20))
    while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        sleep 0.5
        local CONNECTED_SSID
        CONNECTED_SSID=$(iwgetid -r 2>/dev/null)
        if [ "$CONNECTED_SSID" = "$SSID" ]; then
            local HOME_IP
            HOME_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v "^$" | head -1)
            _pa_save_mode "client"
            _pa_save_network "$SSID" "$PASS"
            echo ""
            _pa_ok "Connected to: ${_BYLW}${SSID}"
            [ -n "$HOME_IP" ] && echo -e "  IP: ${_BYLW}${HOME_IP}${_NC}"
            echo ""
            echo -e "  ${_DIM}AP is off. Run ${_BYLW}piap${_DIM} to switch back manually.${_NC}"
            echo -e "  ${_DIM}Watcher will auto-restore AP if this connection drops.${_NC}"
            echo ""
            rm -f "$_PA_CONNECTING_LOCK"
            return 0
        fi
    done

    sudo nmcli device disconnect wlan0 2>/dev/null || true
    return 1
}

# ── piconnect ─────────────────────────────────────────────────
piconnect() {
    _pa_sudo || return 1

    local SSID="$1"
    local PASS="$2"

    if [ -z "$SSID" ]; then
        _pa_err "Usage: piconnect <ssid> [password]"
        return 1
    fi

    # Only prompt for password if not passed as arg and SSID isn't a known open network
    if [ -z "$PASS" ]; then
        read -rsp "  Password for '${SSID}' (leave blank if open network): " PASS
        echo ""
    fi

    echo ""

    _pa_load_state

    if pgrep hostapd > /dev/null 2>&1; then
        echo -e "  ${_BYLW}⚠️  WARNING:${_NC} The AP must shut down to connect to WiFi."
        echo -e "  ${_DIM}Your SSH session will disconnect. This is normal.${_NC}"
        echo -e "  ${_DIM}If connection fails, the AP will restore within 30 seconds.${_NC}"
        echo -e "  ${_DIM}Reconnect to ${_BYLW}${AP_SSID}${_DIM} and SSH to ${_BYLW}10.0.0.1${_NC}"
        echo ""
        read -rp "$(echo -e "  ${_BWHT}Continue? (y/n):${_NC} ")" proceed
        if [ "$proceed" != "y" ]; then
            _pa_warn "Cancelled."
            echo ""
            return 0
        fi
        _pa_info "Turning off AP — you will be disconnected now..."
        sleep 1
        touch "$_PA_CONNECTING_LOCK"
        _pa_stop_ap
    fi

    _pa_info "Connecting to: ${SSID}..."

    if _pa_nmcli_connect "$SSID" "$PASS"; then
        return 0
    fi

    echo ""
    _pa_err "Could not connect to '${SSID}'"
    _pa_warn "Check the password and try again. Restarting AP..."
    rm -f "$_PA_CONNECTING_LOCK"
    _pa_start_ap && _pa_ok "AP is back up: ${_BYLW}${AP_SSID}"
    echo ""
    return 1
}

# ── piupdate ──────────────────────────────────────────────────
piupdate() {
    _pa_sudo || return 1

    echo ""
    echo -e "${_BCYN}  ╔════════════════════════════════════════════╗${_NC}"
    echo -e "${_BCYN}  ║        CHECKING FOR SSHIT UPDATES          ║${_NC}"
    echo -e "${_BCYN}  ╚════════════════════════════════════════════╝${_NC}"
    echo ""

    _REPO_DIR="$_PA_DIR/sshit-repo"
    _BRANCH="main"

    if ! command -v git &>/dev/null; then
        _pa_err "git not installed. Install with: sudo apt install git"
        return 1
    fi

    if [ ! -d "$_REPO_DIR" ]; then
        _pa_info "First time check — cloning repository..."
        git clone -q https://github.com/BruBread/sshit.git "$_REPO_DIR" 2>/dev/null
        if [ $? -ne 0 ]; then
            _pa_err "Failed to clone repository. Check internet connection."
            return 1
        fi
    fi

    cd "$_REPO_DIR" || return 1

    _pa_info "Fetching latest version..."
    git fetch origin "$_BRANCH" --quiet 2>/dev/null
    if [ $? -ne 0 ]; then
        _pa_err "Failed to fetch updates. Check internet connection."
        return 1
    fi

    LOCAL_SHA=$(git rev-parse HEAD 2>/dev/null)
    REMOTE_SHA=$(git rev-parse origin/$_BRANCH 2>/dev/null)

    echo ""
    echo -e "  ${_DIM}Installed: ${_BYLW}${LOCAL_SHA:0:12}${_NC}"
    echo -e "  ${_DIM}Available: ${_BYLW}${REMOTE_SHA:0:12}${_NC}"
    echo ""

    if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
        _pa_ok "You're on the latest version!"
        sudo rm -f "$_PA_DIR/.update_available" 2>/dev/null
        echo ""
        return 0
    fi

    echo -e "${_BCYN}  ┌────────────────────────────────────────────┐${_NC}"
    echo -e "${_BCYN}  │         🎉 UPDATE AVAILABLE! 🎉            │${_NC}"
    echo -e "${_BCYN}  └────────────────────────────────────────────┘${_NC}"
    echo ""

    echo "$REMOTE_SHA" | sudo tee "$_PA_DIR/.update_available" > /dev/null

    read -rp "$(echo -e "  ${_BWHT}Install update now? (y/n):${_NC} ")" confirm
    if [ "$confirm" != "y" ]; then
        _pa_warn "Update skipped. Run 'piupdate' anytime to install."
        echo ""
        return 0
    fi

    echo ""
    _pa_info "Pulling latest version..."
    git pull --ff-only origin "$_BRANCH" --quiet 2>/dev/null
    if [ $? -ne 0 ]; then
        _pa_err "Update failed. Try manually: cd $_REPO_DIR && git pull"
        return 1
    fi

    _pa_info "Installing updated files..."
    sudo cp "$_REPO_DIR/install.sh"    "$_PA_DIR/"
    sudo cp "$_REPO_DIR/picommands.sh" "$_PA_DIR/"
    sudo cp "$_REPO_DIR/netwatcher.sh" "$_PA_DIR/"
    sudo chmod +x "$_PA_DIR"/*.sh

    echo "$REMOTE_SHA" | sudo tee "$_PA_DIR/.version" > /dev/null
    sudo rm -f "$_PA_DIR/.update_available" 2>/dev/null

    echo ""
    _pa_ok "Update installed successfully!"
    echo ""
    echo -e "  ${_BYLW}⚠️  Reload your shell:${_NC}  ${_BWHT}source ~/.bashrc${_NC}"
    echo ""

    read -rp "$(echo -e "  ${_BWHT}Reboot now to apply changes? (y/n):${_NC} ")" reboot_confirm
    if [ "$reboot_confirm" = "y" ]; then
        _pa_info "Rebooting..."
        sleep 1
        sudo reboot
    else
        _pa_warn "Reboot skipped. Run 'pirestart' anytime."
        echo ""
    fi

    return 0
}

# ── pisaved ───────────────────────────────────────────────────
pisaved() {
    local SAVED_FILE="$_PA_DIR/saved_networks"

    echo ""
    echo -e "${_BWHT}  Saved Networks${_NC}"
    echo -e "  ${_DIM}────────────────────────────────────${_NC}"

    if [ ! -f "$SAVED_FILE" ] || [ ! -s "$SAVED_FILE" ]; then
        echo -e "  ${_DIM}No saved networks.${_NC}"
        echo ""
        echo -e "  Use ${_BYLW}piconnect <ssid>${_NC} to connect and save a network."
        echo ""
        return 0
    fi

    local i=1
    while IFS=$'\t' read -r SSID PASS; do
        [ -z "$SSID" ] && continue
        if [ -n "$PASS" ]; then
            echo -e "  ${_BYLW}${i})${_NC} ${SSID}  ${_DIM}(password saved)${_NC}"
        else
            echo -e "  ${_BYLW}${i})${_NC} ${SSID}  ${_DIM}(open network)${_NC}"
        fi
        ((i++))
    done < "$SAVED_FILE"

    echo -e "  ${_DIM}────────────────────────────────────${_NC}"
    echo ""
    read -rp "  Enter number to remove (or q to cancel): " CHOICE
    if [ "$CHOICE" = "q" ] || [ -z "$CHOICE" ]; then
        echo ""
        return 0
    fi

    local j=1
    while IFS=$'\t' read -r SSID PASS; do
        [ -z "$SSID" ] && continue
        if [ "$j" = "$CHOICE" ]; then
            sudo sed -i "/^${SSID}\t/d" "$SAVED_FILE" 2>/dev/null || true
            _pa_ok "Removed: ${SSID}"
            echo ""
            return 0
        fi
        ((j++))
    done < "$SAVED_FILE"

    _pa_err "Invalid choice."
    echo ""
}

# ── piadd ─────────────────────────────────────────────────────
piadd() {
    local SSID="$1"
    local PASS="$2"

    echo ""

    if [ -z "$SSID" ]; then
        read -rp "  Network name (SSID): " SSID
        if [ -z "$SSID" ]; then
            _pa_err "SSID cannot be empty."
            echo ""
            return 1
        fi
    fi

    if [ -z "$PASS" ]; then
        read -rsp "  Password (leave blank if open network): " PASS
        echo ""
    fi

    _pa_save_network "$SSID" "$PASS"
    _pa_ok "Saved: ${_BYLW}${SSID}"
    if [ -z "$PASS" ]; then
        echo -e "  ${_DIM}(open network)${_NC}"
    fi
    echo ""
    echo -e "  ${_DIM}The Pi will auto-connect to this network when in range.${_NC}"
    echo ""
}

# ── pirestart ─────────────────────────────────────────────────
pirestart() {
    _pa_sudo || return 1

    echo ""
    read -rp "$(echo -e "  ${_BWHT}Reboot the Pi now? (y/n):${_NC} ")" confirm
    if [ "$confirm" = "y" ]; then
        _pa_info "Rebooting..."
        sleep 1
        sudo reboot
    else
        _pa_warn "Reboot cancelled."
        echo ""
    fi
}

# ── Auto-check on login ───────────────────────────────────────
_pa_check_update_notice() {
    if [ -n "$_PA_UPDATE_CHECKED" ]; then
        return
    fi
    export _PA_UPDATE_CHECKED=1

    if [ ! -f "$_PA_DIR/.update_available" ]; then
        return
    fi

    echo ""
    echo -e "${_BYLW}  ╔════════════════════════════════════════════╗${_NC}"
    echo -e "${_BYLW}  ║     ⚠️  SSHIT UPDATE AVAILABLE  ⚠️         ║${_NC}"
    echo -e "${_BYLW}  ╚════════════════════════════════════════════╝${_NC}"
    echo ""
    echo -e "  ${_DIM}Run ${_BWHT}piupdate${_DIM} to install the latest version${_NC}"
    echo ""
}

if [[ $- == *i* ]]; then
    _pa_check_update_notice
fi
