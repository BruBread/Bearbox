#!/bin/bash
# install_bbcommands.sh
# Installs all bbcommands as real executables in /usr/local/bin.
# Run once with: sudo bash install_bbcommands.sh
# After this, every bbcommand works in any shell with no sourcing needed.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
    bbstart bbstop bbrestart bbstatus bblogs bbshutdown
    bbedit bbupdate bbconfig bbinstall bbscreen
    bbwifi bbdisconnect bbsave bbip bbnetwork bboffline bbonline
    bbrotate
    bbpentest bbpencrash
    bbgitfix
    bbreset
    bbhelp
)

echo "Installing bbcommands to /usr/local/bin..."
for cmd in "${COMMANDS[@]}"; do
    src="$SCRIPT_DIR/$cmd"
    if [ ! -f "$src" ]; then
        echo "  SKIP $cmd (not found in $SCRIPT_DIR)"
        continue
    fi
    cp "$src" "/usr/local/bin/$cmd"
    chmod +x "/usr/local/bin/$cmd"
    echo "  OK   $cmd"
done

# bbedit: keep as alias in .bashrc since scripts can't cd the calling shell.
# Only add it if it's not already there.
if ! grep -q "alias bbedit" /home/bearbox/.bashrc 2>/dev/null; then
    echo "" >> /home/bearbox/.bashrc
    echo "# bbedit — kept as alias because scripts can't cd the calling shell" >> /home/bearbox/.bashrc
    echo "alias bbedit='cd ~/bearbox'" >> /home/bearbox/.bashrc
    echo "  OK   bbedit (added as alias to ~/.bashrc)"
fi

echo ""
echo "Done. All bbcommands available system-wide — no sourcing needed."
echo "Open a new shell or run: hash -r"
