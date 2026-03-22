#!/bin/bash
# ============================================================
#  BearBox — AP Mode Test Script
#  Tests hostapd + dnsmasq setup safely.
#  Run: sudo bash test_ap.sh
#  Stop: Ctrl+C — auto tears everything down
# ============================================================

AP_SSID="BearBox-AP"
AP_PASS="Bearbox123"
AP_IFACE="wlan1"
ETH_IFACE="eth0"
AP_IP="10.0.0.1"
AP_SUBNET="10.0.0.0/24"
AP_DHCP_START="10.0.0.10"
AP_DHCP_END="10.0.0.50"

BGRN='\033[1;32m'
BRED='\033[1;31m'
BCYN='\033[1;36m'
BYLW='\033[1;33m'
DIM='\033[2m'
NC='\033[0m'

# ── CLEANUP ───────────────────────────────────────────────────
cleanup() {
    echo ""
    echo -e "${BYLW}Tearing down AP...${NC}"

    # stop services
    systemctl stop hostapd   2>/dev/null || true
    systemctl stop dnsmasq   2>/dev/null || true
    pkill hostapd            2>/dev/null || true
    pkill dnsmasq            2>/dev/null || true

    # flush iptables rules we added
    iptables -D FORWARD -i $AP_IFACE -o $ETH_IFACE -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i $ETH_IFACE -o $AP_IFACE \
        -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
    iptables -t nat -D POSTROUTING -o $ETH_IFACE -j MASQUERADE 2>/dev/null || true

    # restore interface
    ip addr flush dev $AP_IFACE  2>/dev/null || true
    ip link set $AP_IFACE down   2>/dev/null || true

    # restore dnsmasq config if we backed it up
    if [ -f /etc/dnsmasq.conf.bb_backup ]; then
        mv /etc/dnsmasq.conf.bb_backup /etc/dnsmasq.conf
    fi

    # restore hostapd config
    if [ -f /etc/hostapd/hostapd.conf.bb_backup ]; then
        mv /etc/hostapd/hostapd.conf.bb_backup /etc/hostapd/hostapd.conf
    fi

    # re-enable NetworkManager on wlan1
    nmcli device set $AP_IFACE managed yes 2>/dev/null || true

    echo -e "${BGRN}✓ AP torn down cleanly${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# ── ROOT CHECK ────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "Run as root: sudo bash test_ap.sh"
    exit 1
fi

echo ""
echo -e "${BGRN}BearBox AP Mode Test${NC}"
echo -e "${DIM}SSID: $AP_SSID  |  Password: $AP_PASS  |  IP: $AP_IP${NC}"
echo -e "${DIM}Press Ctrl+C to stop and clean up${NC}"
echo ""

# ── CHECK INTERFACES ──────────────────────────────────────────
echo -e "${BCYN}Checking interfaces...${NC}"
if ! ip link show $AP_IFACE &>/dev/null; then
    echo -e "${BRED}✗ $AP_IFACE not found — plug in TL-WN722N${NC}"
    exit 1
fi
if ! ip link show $ETH_IFACE &>/dev/null; then
    echo -e "${BRED}✗ $ETH_IFACE not found — plug in ethernet${NC}"
    exit 1
fi
echo -e "${BGRN}✓ Both interfaces found${NC}"

# ── INSTALL DEPS ──────────────────────────────────────────────
echo -e "${BCYN}Installing hostapd and dnsmasq...${NC}"
apt install -y hostapd dnsmasq -qq > /dev/null 2>&1
echo -e "${BGRN}✓ Dependencies installed${NC}"

# ── STOP CONFLICTING SERVICES ─────────────────────────────────
echo -e "${BCYN}Stopping conflicting services...${NC}"
systemctl stop hostapd  2>/dev/null || true
systemctl stop dnsmasq  2>/dev/null || true
# tell NetworkManager to leave wlan1 alone
nmcli device set $AP_IFACE managed no 2>/dev/null || true
echo -e "${BGRN}✓ Done${NC}"

# ── CONFIGURE INTERFACE ───────────────────────────────────────
echo -e "${BCYN}Configuring $AP_IFACE...${NC}"
ip link set $AP_IFACE up
ip addr flush dev $AP_IFACE
ip addr add $AP_IP/24 dev $AP_IFACE
echo -e "${BGRN}✓ $AP_IFACE set to $AP_IP${NC}"

# ── HOSTAPD CONFIG ────────────────────────────────────────────
echo -e "${BCYN}Writing hostapd config...${NC}"
[ -f /etc/hostapd/hostapd.conf ] && \
    cp /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bb_backup

cat > /tmp/bb_hostapd.conf << EOF
interface=$AP_IFACE
driver=nl80211
ssid=$AP_SSID
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$AP_PASS
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
echo -e "${BGRN}✓ hostapd config written${NC}"

# ── DNSMASQ CONFIG ────────────────────────────────────────────
echo -e "${BCYN}Writing dnsmasq config...${NC}"
[ -f /etc/dnsmasq.conf ] && \
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.bb_backup

cat > /tmp/bb_dnsmasq.conf << EOF
interface=$AP_IFACE
dhcp-range=$AP_DHCP_START,$AP_DHCP_END,255.255.255.0,24h
dhcp-option=3,$AP_IP
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
log-queries
log-dhcp
EOF
echo -e "${BGRN}✓ dnsmasq config written${NC}"

# ── IP FORWARDING ─────────────────────────────────────────────
echo -e "${BCYN}Enabling IP forwarding...${NC}"
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -A FORWARD -i $AP_IFACE -o $ETH_IFACE -j ACCEPT
iptables -A FORWARD -i $ETH_IFACE -o $AP_IFACE \
    -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -t nat -A POSTROUTING -o $ETH_IFACE -j MASQUERADE
echo -e "${BGRN}✓ IP forwarding enabled${NC}"

# ── START SERVICES ────────────────────────────────────────────
echo -e "${BCYN}Starting hostapd...${NC}"
hostapd /tmp/bb_hostapd.conf -B
if [ $? -ne 0 ]; then
    echo -e "${BRED}✗ hostapd failed to start!${NC}"
    cleanup
fi
echo -e "${BGRN}✓ hostapd running${NC}"

echo -e "${BCYN}Starting dnsmasq...${NC}"
dnsmasq --conf-file=/tmp/bb_dnsmasq.conf
echo -e "${BGRN}✓ dnsmasq running${NC}"

# ── SUCCESS ───────────────────────────────────────────────────
echo ""
echo -e "${BGRN}════════════════════════════════════${NC}"
echo -e "${BGRN}  BearBox-AP is LIVE!${NC}"
echo -e "${BGRN}════════════════════════════════════${NC}"
echo -e "  SSID:     ${BYLW}$AP_SSID${NC}"
echo -e "  Password: ${BYLW}$AP_PASS${NC}"
echo -e "  Pi IP:    ${BYLW}$AP_IP${NC}"
echo ""
echo -e "  ${DIM}Connect your phone to BearBox-AP${NC}"
echo -e "  ${DIM}Then SSH: ssh bearbox@$AP_IP${NC}"
echo ""
echo -e "  ${DIM}Press Ctrl+C to stop${NC}"
echo ""

# ── KEEP ALIVE + SHOW CLIENTS ─────────────────────────────────
while true; do
    # show connected clients
    clients=$(arp -i $AP_IFACE -n 2>/dev/null | grep -v "incomplete" | \
              grep -v "Address" | awk '{print $1}' | grep -v "^$")
    count=$(echo "$clients" | grep -c . 2>/dev/null || echo 0)

    printf "\r  ${BCYN}Connected clients: ${BYLW}%s${NC}  %s    " \
           "$count" "$(date +%H:%M:%S)"

    sleep 2
done