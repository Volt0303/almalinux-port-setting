#!/usr/bin/env bash
# Build self-contained executables. RUN THIS ON THE AlmaLinux TARGET
# (PyInstaller bundles the host's glibc/tkinter, so it must match the
# machines the binary will run on).
#
#   sudo dnf install -y python3 python3-tkinter
#   bash build.sh
#
# Output: dist/ipset-gui, dist/ipset-cli, dist/config/, dist/操作マニュアル.md
set -euo pipefail
cd "$(dirname "$0")"

echo ">> creating venv"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install pyinstaller openpyxl

echo ">> building CLI (headless)"
pyinstaller --onefile --name ipset-cli \
    --hidden-import openpyxl run_cli.py

echo ">> building GUI (Tkinter)"
pyinstaller --onefile --name ipset-gui \
    --hidden-import openpyxl run_gui.py

echo ">> staging config + manual + sample"
mkdir -p dist/config dist/logs
cp -n config/config_intel.ini.example dist/config/ 2>/dev/null || true
[ -f config/config_intel.ini ] && cp config/config_intel.ini dist/config/ || true
cp docs/操作マニュアル.md dist/ 2>/dev/null || true
cp IPsetting_sample.csv dist/ 2>/dev/null || true

echo ">> done. Artifacts in ./dist"
ls -1 dist
