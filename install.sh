#!/bin/bash
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
echo -e "  ${DIM}NEXUS build — live ticket-sales display${NC}"
echo -e "  ${DIM}github.com/BruBread/Bearbox (nexus branch)${NC}"
echo ""
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
    python3-pip
    fonts-dejavu
    network-manager
    ntpdate
)
for pkg in "${PACKAGES[@]}"; do
    [[ "$pkg" == \#* ]] && continue
    (apt install -y -qq "$pkg" 2>/dev/null) &
    spinner $! "Installing $pkg"
done
ok "All dependencies installed"


# ── PYTHON PIP PACKAGES ───────────────────────────────────────
step "Installing Python packages..."
divider
PIP_PACKAGES=(
    pillow
    numpy
    websocket-client
    lgpio
)
for pkg in "${PIP_PACKAGES[@]}"; do
    (pip3 install "$pkg" --break-system-packages -q 2>/dev/null) &
    spinner $! "pip install $pkg"
done
ok "Python packages installed"


cd /home/bearbox
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
    info "After reboot, run: sudo bash ~/bearbox/install.sh"
    info "(bbinstall isn't set up yet this early in a fresh install)"
    sleep 2
    cd /tmp/LCD-show && sudo ./LCD35-show
fi


step "Cloning BearBox repository..."
divider
if [ -d "/home/bearbox/bearbox" ]; then
    info "Repo already exists — fetching the nexus branch..."
    (cd /home/bearbox/bearbox && git fetch -q origin && git checkout -f -B nexus origin/nexus) &
    spinner $! "Updating to the nexus branch..."
else
    (git clone -q -b nexus https://github.com/BruBread/Bearbox.git /home/bearbox/bearbox) &
    spinner $! "Cloning the nexus branch from GitHub..."
fi
chown -R bearbox:bearbox /home/bearbox/bearbox
ok "Repository ready at /home/bearbox/bearbox (nexus branch)"


# ── FONTS ─────────────────────────────────────────────────────
step "Installing custom fonts..."
divider
mkdir -p /home/bearbox/.fonts
cp /home/bearbox/bearbox/fonts/*.ttf /home/bearbox/.fonts/ 2>/dev/null || true
fc-cache -fv /home/bearbox/.fonts > /dev/null 2>&1 &
spinner $! "Loading fonts..."
ok "Fonts ready"


# ── SSH ───────────────────────────────────────────────────────
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


# ── ALIASES ───────────────────────────────────────────────────
step "Setting up shortcuts..."
divider
grep -q "bearbox/bashrc_aliases" /home/bearbox/.bashrc || \
    echo "source ~/bearbox/bashrc_aliases" >> /home/bearbox/.bashrc
ok "Shortcuts ready"


# ── BBCOMMANDS ────────────────────────────────────────────────
step "Installing bbcommands..."
divider
(bash /home/bearbox/bearbox/bbcommands/install_bbcommands.sh) &
spinner $! "Installing bb commands to /usr/local/bin..."
ok "bbcommands installed system-wide"


# ── WIFI ─────────────────────────────────────────────────────
info "Booth Wi-Fi (NexusV, walawifi) is joined at runtime by nexus.py — nothing to configure here."


# ── SERVICE ───────────────────────────────────────────────────
step "Installing BearBox service..."
divider
(cp /home/bearbox/bearbox/services/bearbox.service /etc/systemd/system/ && \
    systemctl daemon-reload && \
    systemctl enable bearbox) &
spinner $! "Enabling BearBox autostart..."
ok "BearBox will start on boot"


# ── DONE ─────────────────────────────────────────────────────
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
echo -e "  ${BGRN}BearBox NEXUS is installed and ready!${NC}"
echo ""
echo -e "  ${CYN}On boot it joins the booth Wi-Fi, finds the hub, and shows${NC}"
echo -e "  ${CYN}live ticket sales. Tap the screen to toggle the robot eyes.${NC}"
echo ""
echo -e "  ${CYN}SSH from your PC (no password):${NC}"
echo -e "  ${DIM}ssh bearbox@bearbox.local${NC}"
echo ""
echo -e "  ${CYN}Update anytime (after pushing to the nexus branch):${NC}"
echo -e "  ${DIM}bbnexus${NC}"
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