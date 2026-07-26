#!/usr/bin/env bash
# One-time setup for a production device.
# Copy dist/ to /opt/ipset, then place a desktop shortcut.
#
# Usage (run as root or with sudo):
#   sudo bash setup_desktop.sh
#
# After this, the operator double-clicks "LAN IP設定ツール" on the desktop.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR=/opt/ipset
DESKTOP_FILE=/usr/local/share/applications/ipset-gui.desktop

if [ ! -d "$SCRIPT_DIR/dist" ]; then
    echo "ERROR: dist/ not found. Run 'bash build.sh' first, then re-run this script." >&2
    exit 1
fi

echo ">> installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/dist/." "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/ipset-gui" "$INSTALL_DIR/launch_gui.sh" 2>/dev/null || true

# Allow operator to run nmcli via sudo without a password prompt
SUDOERS_LINE="%wheel ALL=(ALL) NOPASSWD: /opt/ipset/ipset-gui, /opt/ipset/launch_gui.sh"
if ! grep -qF "$SUDOERS_LINE" /etc/sudoers.d/ipset 2>/dev/null; then
    echo "$SUDOERS_LINE" > /etc/sudoers.d/ipset
    chmod 440 /etc/sudoers.d/ipset
    echo ">> sudoers entry added"
fi

echo ">> installing desktop shortcut"
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=LAN IP設定ツール
Comment=6ポートLAN IPアドレス自動設定・照合ツール
Exec=bash -c "xhost +si:localuser:root; sudo -E DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY /opt/ipset/ipset-gui"
Icon=network-wired
Terminal=false
Categories=System;Network;
StartupNotify=true
EOF

update-desktop-database /usr/local/share/applications/ 2>/dev/null || true
echo ">> done. Shortcut: $DESKTOP_FILE"
echo "   Operators can now launch from the applications menu: 'LAN IP設定ツール'"
