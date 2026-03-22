#!/bin/bash
# ============================================================
#  BearBox — Install Script
#  Run: sudo bash install.sh
# ============================================================

set -e

# ── COLORS ───────────────────────────────────────────────────
BGRN='\033[1;32m'
BYLW='\033[1;33m'
BCYN='\033[1;36m'
BWHT='\033[1;37m'
BRED='\033[1;31m'
GRN='\033[0;32m'
RED='\033[0;31m'
CYN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

# ── TERMINAL SIZE ─────────────────────────────────────────────
COLS=$(tput cols 2>/dev/null || echo 80)
ROWS=$(tput lines 2>/dev/null || echo 24)

# ── STEPS ─────────────────────────────────────────────────────
TOTAL_STEPS=9
CURRENT_STEP=0
CURRENT_MSG="Initializing..."
CURRENT_STATUS=""

# ── UI FUNCTIONS ──────────────────────────────────────────────

hide_cursor() { tput civis 2>/dev/null; }
show_cursor() { tput cnorm 2>/dev/null; }
clear_screen() { clear; }

draw_bar() {
    local pct=$1
    local w=$((COLS - 4))
    local filled=$(( w * pct / 100 ))
    local empty=$(( w - filled ))
    printf "  ${BGRN}"
    printf '%0.s█' $(seq 1 $filled) 2>/dev/null || printf '%*s' $filled | tr ' ' '█'
    printf "${DIM}"
    printf '%0.s░' $(seq 1 $empty) 2>/dev/null || printf '%*s' $empty | tr ' ' '░'
    printf "${NC}"
}

draw_ui() {
    local pct=$(( CURRENT_STEP * 100 / TOTAL_STEPS ))
    clear_screen

    # banner
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
    echo ""
    echo -e "  ${DIM}────────────────────────────────────────────────────────────${NC}"
    echo ""

    # step list — show all steps, highlight current
    local steps=(
        "Update system packages"
        "Install dependencies"
        "Check LCD driver"
        "Install custom fonts"
        "Clone BearBox repo"
        "Configure SSH access"
        "Install udev rules"
        "Configure WiFi auto-connect"
        "Install BearBox service"
    )

    for i in "${!steps[@]}"; do
        local num=$((i + 1))
        if [ $num -lt $CURRENT_STEP ]; then
            echo -e "  ${BGRN}✓${NC}  ${DIM}${steps[$i]}${NC}"
        elif [ $num -eq $CURRENT_STEP ]; then
            echo -e "  ${BCYN}▶${NC}  ${BWHT}${steps[$i]}${NC}"
        else
            echo -e "  ${DIM}○  ${steps[$i]}${NC}"
        fi
    done

    echo ""
    echo -e "  ${DIM}────────────────────────────────────────────────────────────${NC}"
    echo ""

    # progress bar
    draw_bar $pct
    echo ""
    printf "  ${BCYN}%d%%${NC}  ${DIM}%s${NC}\n" $pct "$CURRENT_MSG"

    # status line
    if [ -n "$CURRENT_STATUS" ]; then
        printf "  ${DIM}%s${NC}\n" "$CURRENT_STATUS"
    fi
}

begin_step() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    CURRENT_MSG="$1"
    CURRENT_STATUS=""
    draw_ui
}

set_status() {
    CURRENT_STATUS="$1"
    draw_ui
}

finish_step() {
    CURRENT_STATUS="✓ $1"
    draw_ui
    sleep 0.3
}

fail() {
    show_cursor
    echo -e "\n  ${BRED}✗${NC}  ${RED}ERROR: $1${NC}\n"
    exit 1
}

# ── CLEANUP ON EXIT ───────────────────────────────────────────
trap show_cursor EXIT
hide_cursor
clear_screen

# ── ROOT CHECK ────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    show_cursor
    echo -e "\n  Run as root: sudo bash install.sh\n"
    exit 1
fi

# ── CONFIRM ───────────────────────────────────────────────────
draw_ui
echo ""
show_cursor
read -p "$(echo -e "  ${BWHT}Ready to install BearBox. Continue? (y/n):${NC} ")" confirm
if [ "$confirm" != "y" ]; then
    echo -e "\n  ${DIM}Aborted.${NC}\n"
    exit 0
fi
hide_cursor

# ── STEP 1: UPDATE ────────────────────────────────────────────
begin_step "Updating system packages..."
set_status "Running apt update..."
apt update -qq > /dev/null 2>&1
set_status "Running apt upgrade..."
apt upgrade -y -qq > /dev/null 2>&1
finish_step "System up to date"

# ── STEP 2: DEPENDENCIES ──────────────────────────────────────
begin_step "Installing dependencies..."
PACKAGES=(
    git python3-pygame python3-psutil fonts-dejavu
    aircrack-ng libts-dev evtest python3-pip
    udev network-manager macchanger ntpdate pillow
)
for pkg in "${PACKAGES[@]}"; do
    set_status "Installing $pkg..."
    apt install -y -qq "$pkg" > /dev/null 2>&1 || true
done
pip3 install pillow numpy --break-system-packages -q > /dev/null 2>&1 || true
finish_step "All dependencies installed"

# ── STEP 3: LCD DRIVER ────────────────────────────────────────
begin_step "Checking LCD driver..."
if [ -e /dev/fb1 ]; then
    finish_step "LCD driver already installed (/dev/fb1 found)"
else
    set_status "LCD not found — cloning GoodTFT LCD-show..."
    git clone -q https://github.com/goodtft/LCD-show.git /tmp/LCD-show > /dev/null 2>&1
    chmod +x /tmp/LCD-show/LCD35-show
    set_status "Installing LCD35 driver — Pi will reboot, run bbinstall after!"
    sleep 3
    cd /tmp/LCD-show && sudo ./LCD35-show
fi

# ── STEP 4: FONTS ─────────────────────────────────────────────
begin_step "Installing custom fonts..."
mkdir -p /home/bearbox/.fonts
cp /home/bearbox/bearbox/fonts/*.ttf /home/bearbox/.fonts/ 2>/dev/null || true
fc-cache -fv /home/bearbox/.fonts > /dev/null 2>&1
finish_step "Fonts ready"

# ── STEP 5: CLONE REPO ────────────────────────────────────────
begin_step "Cloning BearBox repository..."
if [ -d "/home/bearbox/bearbox" ]; then
    set_status "Repo exists — pulling latest..."
    cd /home/bearbox/bearbox && git pull -q > /dev/null 2>&1
else
    set_status "Cloning from GitHub..."
    git clone -q https://github.com/BruBread/bearbox.git /home/bearbox/bearbox > /dev/null 2>&1
fi
chown -R bearbox:bearbox /home/bearbox/bearbox
finish_step "Repository ready"

# ── STEP 6: SSH ───────────────────────────────────────────────
begin_step "Configuring SSH access..."
mkdir -p /home/bearbox/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDknWDgOiUKvoSZJZTUQ1o2KSz62dbNgSEOPje7Sk4eG bearbox" \
    >> /home/bearbox/.ssh/authorized_keys
sort -u /home/bearbox/.ssh/authorized_keys -o /home/bearbox/.ssh/authorized_keys
chmod 700 /home/bearbox/.ssh
chmod 600 /home/bearbox/.ssh/authorized_keys
chown -R bearbox:bearbox /home/bearbox/.ssh
finish_step "SSH key configured — no password needed from your PC"

# ── STEP 7: UDEV ──────────────────────────────────────────────
begin_step "Installing udev rules..."
if [ -f /home/bearbox/bearbox/udev/99-bearbox.rules ]; then
    set_status "Copying udev rules..."
    cp /home/bearbox/bearbox/udev/99-bearbox.rules /etc/udev/rules.d/
    udevadm control --reload-rules
    udevadm trigger
    finish_step "udev rules installed"
else
    finish_step "No udev rules found — skipping"
fi

# ── STEP 7.5: ALIASES ─────────────────────────────────────────
set_status "Setting up shortcuts..."
grep -q "bearbox/bashrc_aliases" /home/bearbox/.bashrc || \
    echo "source ~/bearbox/bashrc_aliases" >> /home/bearbox/.bashrc

# ── STEP 8: WIFI ──────────────────────────────────────────────
begin_step "Configuring WiFi auto-connect..."
if [ -f /home/bearbox/bearbox/config.json ]; then
    SSID=$(python3 -c "import json; c=json.load(open('/home/bearbox/bearbox/config.json')); print(c['hotspot_ssid'])")
    PSK=$(python3 -c "import json; c=json.load(open('/home/bearbox/bearbox/config.json')); print(c['hotspot_password'])")
    set_status "Configuring $SSID..."
    if ! grep -q "$SSID" /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null; then
        cat >> /etc/wpa_supplicant/wpa_supplicant.conf << EOF

network={
    ssid="$SSID"
    psk="$PSK"
    priority=10
}
EOF
        finish_step "WiFi auto-connect configured for $SSID"
    else
        finish_step "WiFi already configured for $SSID"
    fi
else
    finish_step "No config.json — skipping WiFi setup"
fi

# ── STEP 9: SERVICE ───────────────────────────────────────────
begin_step "Installing BearBox service..."
set_status "Copying service file..."
cp /home/bearbox/bearbox/services/bearbox.service /etc/systemd/system/
set_status "Enabling autostart..."
systemctl daemon-reload
systemctl enable bearbox
finish_step "BearBox will start on boot"

# ── DONE ──────────────────────────────────────────────────────
CURRENT_STEP=$TOTAL_STEPS
CURRENT_MSG="Installation complete!"
CURRENT_STATUS=""
draw_ui

echo ""
echo -e "${BGRN}"
echo '  ██████╗  ██████╗ ███╗   ██╗███████╗██╗'
echo '  ██╔══██╗██╔═══██╗████╗  ██║██╔════╝██║'
echo '  ██║  ██║██║   ██║██╔██╗ ██║█████╗  ██║'
echo '  ██║  ██║██║   ██║██║╚██╗██║██╔══╝  ╚═╝'
echo '  ██████╔╝╚██████╔╝██║ ╚████║███████╗██╗'
echo '  ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚═╝'
echo -e "${NC}"
echo -e "  ${DIM}────────────────────────────────────────────────────────────${NC}"
echo -e "  ${BGRN}BearBox is installed and ready!${NC}"
echo ""
echo -e "  ${CYN}SSH from your PC:${NC}  ${DIM}ssh bearbox@bearbox.local${NC}"
echo -e "  ${CYN}Update anytime:${NC}    ${DIM}bbupdate${NC}"
echo -e "  ${CYN}Launch clock:${NC}      ${DIM}bbclock${NC}"
echo -e "  ${DIM}────────────────────────────────────────────────────────────${NC}"
echo ""

show_cursor
read -p "$(echo -e "  ${BWHT}Reboot now? (y/n):${NC} ")" reboot_confirm
if [ "$reboot_confirm" = "y" ]; then
    echo -e "\n  ${BGRN}Rebooting...${NC}\n"
    sleep 1
    reboot
else
    echo -e "\n  ${DIM}Remember to reboot before using BearBox!${NC}\n"
fi