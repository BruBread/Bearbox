#!/bin/bash
# ============================================================
#  SSHit — Installer
#  Makes headless Pi SSH access dead simple.
#  Usage: sudo bash install.sh
# ============================================================

set -e

# ── Colors ────────────────────────────────────────────────────
BLK='\033[0;30m'
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
BLU='\033[0;34m'
PRP='\033[0;35m'
CYN='\033[0;36m'
WHT='\033[0;37m'
BGRN='\033[1;32m'
BYLW='\033[1;33m'
BCYN='\033[1;36m'
BWHT='\033[1;37m'
BRED='\033[1;31m'
DIM='\033[2m'
NC='\033[0m'

clear

# ── Helpers ───────────────────────────────────────────────────
spinner() {
    local pid=$1
    local msg=$2
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    while kill -0 $pid 2>/dev/null; do
        i=$(( (i+1) % 10 ))
        printf "\r  ${BCYN}${spin:$i:1}${NC}  ${DIM}${msg}${NC}"
        sleep 0.1
    done
    printf "\r  ${BGRN}✓${NC}  ${msg}\n"
}

step() {
    echo -e "\n  ${BYLW}▶${NC}  ${BWHT}$1${NC}"
}

ok() {
    echo -e "  ${BGRN}✓${NC}  ${GRN}$1${NC}"
}

err() {
    echo -e "  ${BRED}✗${NC}  ${RED}$1${NC}"
    exit 1
}

info() {
    echo -e "  ${CYN}•${NC}  ${DIM}$1${NC}"
}

warn() {
    echo -e "  ${BYLW}!${NC}  ${YLW}$1${NC}"
}

divider() {
    echo -e "  ${DIM}────────────────────────────────────────────────${NC}"
}

# ── BANNER ────────────────────────────────────────────────────
echo ""
echo -e "${BGRN}"
echo '   ██████╗  ██████╗ ██╗  ██╗██╗████████╗'
echo '  ██╔════╝ ██╔════╝ ██║  ██║██║╚══██╔══╝'
echo '  ╚█████╗  ╚█████╗  ███████║██║   ██║   '
echo '   ╚═══██╗  ╚═══██╗ ██╔══██║██║   ██║   '
echo '  ██████╔╝ ██████╔╝ ██║  ██║██║   ██║   '
echo '  ╚═════╝  ╚═════╝  ╚═╝  ╚═╝╚═╝   ╚═╝   '
echo -e "${NC}"
echo -e "  ${DIM}Dead-simple headless Pi SSH access — by BruBread${NC}"
echo -e "  ${DIM}github.com/BruBread/sshit${NC}"
echo ""
divider
echo -e "  ${BYLW}What this installs:${NC}"
echo -e "  ${CYN}📡${NC} Wi-Fi AP named  ${BGRN}pi-$(whoami)${NC}  on boot"
echo -e "  ${CYN}🔒${NC} SSH always on   ${BGRN}10.0.0.1${NC}"
echo -e "  ${CYN}♻️ ${NC} Auto-recovery   ${BGRN}AP restores if network drops${NC}"
echo -e "  ${CYN}⚡${NC} pi* commands    ${BGRN}pihelp, pistatus, pilock...${NC}"
divider
echo ""

# ── ROOT CHECK ────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    err "Run as root: sudo bash install.sh"
fi

# ── CONFIRM ───────────────────────────────────────────────────
echo -e "  ${BYLW}Ready to install SSHit on this Pi.${NC}"
echo -e "  ${DIM}This will install hostapd, dnsmasq, and set up${NC}"
echo -e "  ${DIM}two systemd services for AP and auto-recovery.${NC}"
echo ""
read -p "$(echo -e "  ${BWHT}Continue? (y/n):${NC} ")" confirm
[ "$confirm" != "y" ] && echo -e "\n  ${DIM}Aborted.${NC}\n" && exit 0

# ── CONFIG ────────────────────────────────────────────────────
# Get the actual user who ran sudo (not root)
ACTUAL_USER="${SUDO_USER:-$(whoami)}"
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

INSTALL_DIR="$ACTUAL_HOME/.piaccess"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AP_IP="10.0.0.1"
AP_SSID="pi-${ACTUAL_USER}"
AP_IFACE="wlan0"
DHCP_START="10.0.0.10"
DHCP_END="10.0.0.50"

# ── CHECKS ────────────────────────────────────────────────────
echo ""
step "Checking system..."
divider

PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
if echo "$PI_MODEL" | grep -qi "raspberry pi"; then
    ok "Detected: $PI_MODEL"
else
    warn "Could not detect Pi model — continuing anyway"
fi

if ! ip link show "$AP_IFACE" &>/dev/null; then
    err "$AP_IFACE not found. Is Wi-Fi available?"
fi
ok "Wi-Fi interface $AP_IFACE found"

# ── INSTALL DEPS ──────────────────────────────────────────────
step "Installing dependencies..."
divider
(apt-get update -qq) &
spinner $! "Updating package lists..."

(apt-get install -y hostapd dnsmasq network-manager -qq > /dev/null 2>&1) &
spinner $! "Installing hostapd + dnsmasq + network-manager..."

systemctl unmask hostapd 2>/dev/null || true
ok "Dependencies installed"

# ── CREATE INSTALL DIR ────────────────────────────────────────
step "Setting up SSHit files..."
divider
mkdir -p "$INSTALL_DIR"
# Fix ownership if installed with sudo
if [ -n "$SUDO_USER" ]; then
    chown -R "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR"
fi
ok "Created $INSTALL_DIR"

# ── HOSTAPD CONFIG ────────────────────────────────────────────
cat > "$INSTALL_DIR/hostapd.conf" << EOF
interface=${AP_IFACE}
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
# No wpa= line = open network. Run 'sudo pilock' to add a password.
EOF
ok "hostapd config written  →  SSID: ${BYLW}${AP_SSID}${NC}"

# ── DNSMASQ CONFIG ────────────────────────────────────────────
if [ -f /etc/dnsmasq.conf ] && [ ! -f /etc/dnsmasq.conf.sshit_backup ]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.sshit_backup
    info "Backed up existing dnsmasq.conf"
fi
cat > "$INSTALL_DIR/dnsmasq.conf" << EOF
interface=${AP_IFACE}
dhcp-range=${DHCP_START},${DHCP_END},255.255.255.0,24h
dhcp-option=3,${AP_IP}
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
EOF
ok "dnsmasq config written  →  DHCP: ${BYLW}${DHCP_START}-${DHCP_END}${NC}"

# ── STATE FILE ────────────────────────────────────────────────
cat > "$INSTALL_DIR/ap_state" << EOF
AP_SSID=${AP_SSID}
AP_PASS=
AP_IFACE=${AP_IFACE}
AP_IP=${AP_IP}
PA_MODE=ap
EOF
ok "State file written"

# ── SAVED NETWORKS ────────────────────────────────────────────
step "Saved networks (auto-connect)..."
divider
echo -e "  ${DIM}Add networks the Pi should auto-connect to when in range.${NC}"
echo -e "  ${DIM}Leave SSID blank to skip.${NC}"
echo ""

touch "$INSTALL_DIR/saved_networks"
while true; do
    read -p "$(echo -e "  ${BWHT}Network SSID (blank to finish):${NC} ")" _SSID
    [ -z "$_SSID" ] && break
    read -rsp "  Password (blank if open): " _PASS
    echo ""
    printf '%s\t%s\n' "$_SSID" "$_PASS" >> "$INSTALL_DIR/saved_networks"
    ok "Saved: ${BYLW}${_SSID}${NC}"
done
if [ -n "$SUDO_USER" ]; then
    chown "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR/saved_networks"
fi
echo ""
cat > "$INSTALL_DIR/ap_start.sh" << EOF
#!/bin/bash
source ${INSTALL_DIR}/ap_state

# Kill anything holding wlan0
pkill hostapd 2>/dev/null
pkill dnsmasq 2>/dev/null
pkill wpa_supplicant 2>/dev/null
sleep 1

# Tell NetworkManager to hands off wlan0
if command -v nmcli &>/dev/null; then
    nmcli device set "\$AP_IFACE" managed no 2>/dev/null || true
fi

# Bring up wlan0 and configure AP
ip link set "\$AP_IFACE" down
sleep 1
ip link set "\$AP_IFACE" up
ip addr flush dev "\$AP_IFACE"
ip addr add "\$AP_IP/24" dev "\$AP_IFACE"
echo 1 > /proc/sys/net/ipv4/ip_forward

# Start hostapd and dnsmasq
hostapd ${INSTALL_DIR}/hostapd.conf -B
sleep 1
dnsmasq --conf-file=${INSTALL_DIR}/dnsmasq.conf
EOF

cat > "$INSTALL_DIR/ap_stop.sh" << 'EOF'
#!/bin/bash
pkill hostapd 2>/dev/null || true
pkill dnsmasq 2>/dev/null || true
EOF
chmod +x "$INSTALL_DIR/ap_start.sh" "$INSTALL_DIR/ap_stop.sh"

# ── PICOMMANDS ────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/picommands.sh" ]; then
    cp "$SCRIPT_DIR/picommands.sh" "$INSTALL_DIR/picommands.sh"
    chmod +x "$INSTALL_DIR/picommands.sh"
    ok "pi* commands installed"
else
    err "picommands.sh not found — make sure you're running from the cloned repo"
fi

# ── NETWATCHER ────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/netwatcher.sh" ]; then
    cp "$SCRIPT_DIR/netwatcher.sh" "$INSTALL_DIR/netwatcher.sh"
    chmod +x "$INSTALL_DIR/netwatcher.sh"
    ok "netwatcher installed"
else
    err "netwatcher.sh not found — make sure you're running from the cloned repo"
fi

# ── BASHRC ────────────────────────────────────────────────────
BASHRC="$ACTUAL_HOME/.bashrc"
BASHRC_LINE="source $INSTALL_DIR/picommands.sh  # sshit"
if grep -q "sshit" "$BASHRC" 2>/dev/null; then
    warn ".bashrc already configured — skipping"
else
    echo "" >> "$BASHRC"
    echo "$BASHRC_LINE" >> "$BASHRC"
    # Fix ownership if installed with sudo
    if [ -n "$SUDO_USER" ]; then
        chown "$SUDO_USER:$SUDO_USER" "$BASHRC"
    fi
    ok "pi* commands added to ~/.bashrc"
fi

# ── SYSTEMD SERVICES ──────────────────────────────────────────
step "Installing systemd services..."
divider

cat > /etc/systemd/system/piaccess.service << EOF
[Unit]
Description=SSHit Wi-Fi AP
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/sleep 10
ExecStart=/bin/bash ${INSTALL_DIR}/ap_start.sh
ExecStop=/bin/bash ${INSTALL_DIR}/ap_stop.sh

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/pa-netwatcher.service << EOF
[Unit]
Description=SSHit Network Watcher
After=piaccess.service

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStart=/bin/bash ${INSTALL_DIR}/netwatcher.sh

[Install]
WantedBy=multi-user.target
EOF

(systemctl daemon-reload && \
 systemctl enable piaccess && \
 systemctl enable pa-netwatcher) &
spinner $! "Enabling services..."
ok "piaccess + pa-netwatcher enabled on boot"

# ── FINALIZE ──────────────────────────────────────────────────
step "Finalizing installation..."
divider

ok "All configs written"
ok "Services enabled on boot"
info "AP will start automatically on next boot"

# ── DONE ──────────────────────────────────────────────────────
echo ""
echo -e "${BGRN}"
echo '  ██████╗  ██████╗ ███╗   ██╗███████╗██╗'
echo '  ██╔══██╗██╔═══██╗████╗  ██║██╔════╝██║'
echo '  ██║  ██║██║   ██║██╔██╗ ██║█████╗  ██║'
echo '  ██║  ██║██║   ██║██║╚██╗██║██╔══╝  ╚═╝'
echo '  ██████╔╝╚██████╔╝██║ ╚████║███████╗██╗'
echo '  ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚═╝'
echo -e "${NC}"
divider
echo -e "  ${BGRN}SSHit is installed!${NC}"
echo ""
echo -e "  ${BYLW}⚠️  REBOOT REQUIRED${NC}"
echo -e "  ${DIM}Run:  ${BYLW}sudo reboot${NC}"
echo ""
echo -e "  ${DIM}After reboot:${NC}"
echo -e "  ${DIM}1. Join Wi-Fi:  ${BYLW}${AP_SSID}${DIM}  (no password)${NC}"
echo -e "  ${DIM}2. SSH in:      ${BYLW}ssh ${ACTUAL_USER}@${AP_IP}${NC}"
echo ""
echo -e "  ${CYN}Useful commands:${NC}"
echo -e "  ${DIM}pihelp        see all commands${NC}"
echo -e "  ${DIM}pistatus      check AP + connection status${NC}"
echo -e "  ${DIM}sudo pilock   add a password to the AP${NC}"
echo -e "  ${DIM}sudo piwifi   connect Pi to your home network${NC}"
echo -e "  ${DIM}piadd         add a network to auto-connect list${NC}"
echo ""
echo -e "  ${DIM}Reload shell:  ${BYLW}source ~/.bashrc${NC}"
divider
echo ""
