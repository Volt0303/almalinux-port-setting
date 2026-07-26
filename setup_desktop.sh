#!/usr/bin/env bash
# One-time setup for a production device.
# Run as root (or with sudo) AFTER running build.sh.
#
#   sudo bash setup_desktop.sh
#
# Result: a double-clickable "LAN IP設定ツール" icon appears on the desktop.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR=/opt/ipset

# Detect the real user (the one who called sudo, not root)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

if [ ! -d "$SCRIPT_DIR/dist" ]; then
    echo "ERROR: dist/ not found. Run 'bash build.sh' first." >&2
    exit 1
fi

# ── 1. Install binary ────────────────────────────────────────────────────────
echo ">> installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/dist/." "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/ipset-gui" 2>/dev/null || true

# ── 2. Passwordless sudo for this binary only ────────────────────────────────
# Operators are not developers; they must not see a password prompt.
SUDOERS=/etc/sudoers.d/ipset
echo "ALL ALL=(ALL) NOPASSWD: $INSTALL_DIR/ipset-gui" > "$SUDOERS"
chmod 440 "$SUDOERS"
echo ">> sudoers: passwordless launch enabled for $INSTALL_DIR/ipset-gui"

# ── 3. Create the .desktop file ─────────────────────────────────────────────
DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=LAN IP設定ツール
Comment=6ポートLAN IPアドレス自動設定・照合ツール
Exec=bash -c 'xhost +si:localuser:root >/dev/null 2>&1; sudo $INSTALL_DIR/ipset-gui'
Icon=network-wired
Terminal=false
Categories=System;Network;
StartupNotify=true"

# Applications menu (all users)
mkdir -p /usr/local/share/applications
echo "$DESKTOP_CONTENT" > /usr/local/share/applications/ipset-gui.desktop
update-desktop-database /usr/local/share/applications/ 2>/dev/null || true

# Desktop icon (locale-aware: "Desktop" on English, "デスクトップ" on Japanese, etc.)
DESKTOP_DIR=$(sudo -u "$REAL_USER" xdg-user-dir DESKTOP 2>/dev/null || echo "")
if [ -z "$DESKTOP_DIR" ] || [ ! -d "$DESKTOP_DIR" ]; then
    DESKTOP_DIR="$REAL_HOME/Desktop"
fi
if [ -d "$DESKTOP_DIR" ]; then
    echo "$DESKTOP_CONTENT" > "$DESKTOP_DIR/ipset-gui.desktop"
    chmod +x "$DESKTOP_DIR/ipset-gui.desktop"
    chown "$REAL_USER:" "$DESKTOP_DIR/ipset-gui.desktop"
    echo ">> desktop icon placed at $DESKTOP_DIR/ipset-gui.desktop"
else
    echo ">> (Desktop folder not found; shortcut is in the applications menu only)"
fi

echo ""
echo ">> Setup complete."
echo "   The operator can now double-click 'LAN IP設定ツール' to start the tool."
