#!/usr/bin/env bash
# Launcher for the GUI when started from a desktop icon.
# Forwards the X display into the root process (sudo strips it otherwise)
# and logs any startup error to /tmp/ipset-gui.log so failures are visible.

LOG=/tmp/ipset-gui.log
export DISPLAY="${DISPLAY:-:0}"

# Change to the install directory so relative paths (config/, logs/) resolve correctly
cd /opt/ipset

# Allow root to draw on the current user's display
xhost +si:localuser:root >/dev/null 2>&1 || true

# Pick binary if installed, else run from source
if [ -x /opt/ipset/ipset-gui ]; then
    APP=(/opt/ipset/ipset-gui)
elif [ -x "$(dirname "$0")/ipset-gui" ]; then
    APP=("$(dirname "$0")/ipset-gui")
else
    APP=(python3 -m ipset.gui)
fi

echo "=== launch $(date) DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY ===" >> "$LOG"
exec sudo -E env DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" "${APP[@]}" >> "$LOG" 2>&1
