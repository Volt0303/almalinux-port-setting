#!/usr/bin/env bash
# Launcher for 6-port LAN IP setting GUI.
# Run this script directly, or via the .desktop shortcut.
# Works whether the binary (dist/ipset-gui) or source is present.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Allow root to use the current user's X display (needed when sudo drops env)
xhost +si:localuser:root 2>/dev/null || true

if [ -x "$SCRIPT_DIR/dist/ipset-gui" ]; then
    # Built binary
    exec sudo -E "$SCRIPT_DIR/dist/ipset-gui"
else
    # Source fallback
    exec sudo -E python3 -m ipset.gui
fi
