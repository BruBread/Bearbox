set -e
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

divider() {
    echo -e "  ${DIM}────────────────────────────────────────────────${NC}"
}

# ── BANNER ───────────────────────────────────────────────────
echo ""
echo -e "${BGRN}"
echo '  ██████╗ ███████╗ █████╗ ██████╗ ██████╗  ██████╗ ██╗  ██╗'
echo '  ██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝'
echo '  ██████╔╝█████╗  ███████║██████╔╝██████╔╝██║   ██║ ╚███╔╝ '
echo '  ██╔══██╗██╔══╝  ██╔══██║██╔══██╗██╔══██╗██║   ██║ ██╔██╗ '
echo '  ██████╔╝███████╗██║  ██║██║  ██║██████╔╝╚██████╔╝██╔╝ ██╗'
echo '  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝'
echo -e "${NC}"
echo -e "  ${DIM}Hot-swappable Pi Computer — by Bearbruh${NC}"
echo -e "  ${DIM}github.com/BruBread/bearbox${NC}"
echo ""
divider
echo -e "  ${BYLW}Profiles:${NC}"
echo -e "  ${CYN}⚡${NC} TL-WN722N    →  ${BGRN}Pentest Mode${NC}"
echo -e "  ${CYN}🎮${NC} USB Drive    →  ${BGRN}Game Launcher${NC}"
echo -e "  ${CYN}🦆${NC} Rubber Ducky →  ${BGRN}Ducky Scripts${NC}"
echo -e "  ${CYN}📡${NC} BT Adapter   →  ${BGRN}Bluetooth Tools${NC}"
divider
echo ""


if [ "$EUID" -ne 0 ]; then
    err "Run as root: sudo bash install.sh"
fi


echo -e "  ${BYLW}Ready to install BearBox on this machine.${NC}"
echo -e "  ${DIM}This will install packages, clone the repo,${NC}"
echo -e "  ${DIM}set up SSH keys, and configure autostart.${NC}"
echo ""
read -p "$(echo -e "  ${BWHT}Continue? (y/n):${NC} ")" confirm
if [ "$confirm" != "y" ]; then
    echo -e "\n  ${DIM}Aborted.${NC}\n"
    exit 0
fi


echo ""
step "Updating system packages..."
divider
(apt update -qq && apt upgrade -y -qq) &
spinner $! "Updating apt..."
ok "System up to date"


step "Installing dependencies..."
divider
PACKAGES=(
    git
    python3-pygame
    python3-psutil
    fonts-dejavu
    aircrack-ng
    libts-dev
    evtest
    python3-pip
    udev
    network-manager
    macchanger
    ntpdate
    hostapd
    dnsmasq
    # portal dependencies
    python3-flask
    python3-smbus
    i2c-tools
)
for pkg in "${PACKAGES[@]}"; do
    # skip comment lines
    [[ "$pkg" == \#* ]] && continue
    (apt install -y -qq "$pkg" 2>/dev/null) &
    spinner $! "Installing $pkg"
done
ok "All dependencies installed"


# ── PYTHON PIP PACKAGES ───────────────────────────────────────
step "Installing Python packages..."
divider
PIP_PACKAGES=(
    "qrcode[pil]"
    pillow
)
for pkg in "${PIP_PACKAGES[@]}"; do
    (pip3 install "$pkg" --break-system-packages -q 2>/dev/null) &
    spinner $! "pip install $pkg"
done
ok "Python packages installed"


# ── LCD DRIVER ────────────────────────────────────────────────
step "Checking LCD driver..."
divider
if [ -e /dev/fb1 ]; then
    ok "LCD driver already installed (/dev/fb1 found)"
else
    info "LCD driver not found — installing GoodTFT driver..."
    (git clone -q https://github.com/goodtft/LCD-show.git /tmp/LCD-show) &
    spinner $! "Cloning LCD-show..."
    chmod +x /tmp/LCD-show/LCD35-show
    info "Installing LCD35 driver — Pi will reboot automatically"
    info "After reboot, run bbinstall again to continue setup"
    sleep 2
    cd /tmp/LCD-show && sudo ./LCD35-show
    # script reboots Pi here — install.sh will need to be run again
fi


# ── FONTS ─────────────────────────────────────────────────────
step "Installing custom fonts..."
divider
mkdir -p /home/bearbox/.fonts
cp /home/bearbox/bearbox/fonts/*.ttf /home/bearbox/.fonts/ 2>/dev/null || true
fc-cache -fv /home/bearbox/.fonts > /dev/null 2>&1 &
spinner $! "Loading fonts..."
ok "Fonts ready"


step "Cloning BearBox repository..."
divider
if [ -d "/home/bearbox/bearbox" ]; then
    info "Repo already exists — pulling latest..."
    (cd /home/bearbox/bearbox && git pull -q) &
    spinner $! "Pulling latest from GitHub..."
else
    (git clone -q https://github.com/YourUsername/bearbox.git /home/bearbox/bearbox) &
    spinner $! "Cloning from GitHub..."
fi
chown -R bearbox:bearbox /home/bearbox/bearbox
ok "Repository ready at /home/bearbox/bearbox"


step "Configuring SSH access..."
divider
mkdir -p /home/bearbox/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDknWDgOiUKvoSZJZTUQ1o2KSz62dbNgSEOPje7Sk4eG bearbox" \
    >> /home/bearbox/.ssh/authorized_keys
sort -u /home/bearbox/.ssh/authorized_keys -o /home/bearbox/.ssh/authorized_keys
chmod 700 /home/bearbox/.ssh
chmod 600 /home/bearbox/.ssh/authorized_keys
chown -R bearbox:bearbox /home/bearbox/.ssh
ok "SSH key configured — no password needed from your PC"


step "Installing udev rules..."
divider
(cp /home/bearbox/bearbox/udev/99-bearbox.rules /etc/udev/rules.d/ && \
    udevadm control --reload-rules && \
    udevadm trigger) &
spinner $! "Installing hotswap rules..."
ok "udev rules installed"


# ── PORTAL: allow Flask to bind port 80 without root ──────────
step "Configuring portal permissions..."
divider
# Allow python3 to bind to port 80 so the portal runs as bearbox user
setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3)) 2>/dev/null || \
    info "setcap failed — portal will fall back to sudo for port 80"
# Allow bearbox to run nmcli and iwlist without password (needed for wifi scan/connect)
SUDOERS_LINE="bearbox ALL=(ALL) NOPASSWD: /usr/bin/nmcli, /usr/sbin/iwlist, /sbin/iwlist, /usr/bin/iwlist"
if ! grep -qF "bearbox ALL=(ALL) NOPASSWD" /etc/sudoers.d/bearbox-portal 2>/dev/null; then
    echo "$SUDOERS_LINE" > /etc/sudoers.d/bearbox-portal
    chmod 440 /etc/sudoers.d/bearbox-portal
    ok "Portal sudoers rule installed"
else
    ok "Portal sudoers rule already present"
fi


# ── PORTAL: enable I2C (for future battery HAT support) ───────
step "Enabling I2C interface..."
divider
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    # Try both paths (Bookworm uses /boot/firmware, older uses /boot)
    CONFIG_PATH="/boot/firmware/config.txt"
    [ -f "$CONFIG_PATH" ] || CONFIG_PATH="/boot/config.txt"
    echo "dtparam=i2c_arm=on" >> "$CONFIG_PATH"
    ok "I2C enabled in $CONFIG_PATH"
else
    ok "I2C already enabled"
fi


# ── Aliases ───────────────────────────────────────────────────
step "Setting up shortcuts..."
divider
grep -q "bearbox/bashrc_aliases" /home/bearbox/.bashrc || \
    echo "source ~/bearbox/bashrc_aliases" >> /home/bearbox/.bashrc
ok "Shortcuts ready"


# ── WIFI AUTO-CONNECT ─────────────────────────────────────────
step "Configuring WiFi auto-connect..."
divider
if [ -f /home/bearbox/bearbox/config.json ]; then
    SSID=$(python3 -c "import json; c=json.load(open('/home/bearbox/bearbox/config.json')); print(c['hotspot_ssid'])")
    PSK=$(python3 -c "import json; c=json.load(open('/home/bearbox/bearbox/config.json')); print(c['hotspot_password'])")
    if ! grep -q "$SSID" /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null; then
        cat >> /etc/wpa_supplicant/wpa_supplicant.conf << EOF

network={
    ssid="$SSID"
    psk="$PSK"
    priority=10
}
EOF
        ok "WiFi auto-connect configured for $SSID"
    else
        ok "WiFi already configured for $SSID"
    fi
else
    info "No config.json found — skipping WiFi setup"
    info "Create config.json and re-run install.sh"
fi


step "Installing BearBox service..."
divider
(cp /home/bearbox/bearbox/services/bearbox.service /etc/systemd/system/ && \
    systemctl daemon-reload && \
    systemctl enable bearbox) &
spinner $! "Enabling BearBox autostart..."
ok "BearBox will start on boot"


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
echo -e "  ${BGRN}BearBox is installed and ready!${NC}"
echo ""
echo -e "  ${CYN}Plug in your devices to get started:${NC}"
echo -e "  ${DIM}⚡ TL-WN722N   →  Pentest mode loads automatically${NC}"
echo -e "  ${DIM}🎮 USB Drive   →  Game launcher loads automatically${NC}"
echo -e "  ${DIM}🦆 Rubber Ducky → Ducky scripts load automatically${NC}"
echo ""
echo -e "  ${CYN}SSH from your PC (no password):${NC}"
echo -e "  ${DIM}ssh bearbox@bearbox.local${NC}"
echo ""
echo -e "  ${CYN}When offline, connect to BearBox-AP and visit:${NC}"
echo -e "  ${DIM}http://bearbox.local${NC}"
echo ""
echo -e "  ${CYN}Update BearBox anytime:${NC}"
echo -e "  ${DIM}cd ~/bearbox && git pull${NC}"
divider
echo ""
read -p "$(echo -e "  ${BWHT}Reboot now to apply all changes? (y/n):${NC} ")" reboot_confirm
if [ "$reboot_confirm" = "y" ]; then
    echo -e "\n  ${BGRN}Rebooting...${NC}\n"
    sleep 1
    reboot
else
    echo -e "\n  ${DIM}Remember to reboot before using BearBox!${NC}\n"
fi