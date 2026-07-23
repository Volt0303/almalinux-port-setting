# 6ポートLAN IPアドレス自動設定・照合システム

AlmaLinux 9.8 搭載産業用PC（約400台）の6ポートLANへ、支給CSV/Excelを元に
IPv4固定設定を自動適用し、実適用値を読み戻して照合、CSVログに記録するツール。

- 発注: 城迫 様（エフアンドエフ(株)）  受注: ユキソフト
- 対象OS: AlmaLinux 9.7 / 9.8（Python 3.9, NetworkManager/nmcli）
- 対象HW: ASRock IMB-A8000M + Intel I350-T4V2（オンボード2 + 増設4 = 6ポート）

## 開発環境の前提
- コアロジック（loader/netmask/compare/logwriter）はOS非依存 → Ubuntu開発機で単体テスト可
- nmcli適用/読み戻し（applier/reader/cli）は **AlmaLinux実機で検証**（開発機では dry-run のみ）
- コードは **Python 3.9互換** で書く（実機が3.9のため）

## 構成
```
ipset/
  core/  loader netmask applier reader compare logwriter
  cli.py   headless pipeline（Step 9）
  gui.py   Tkinter thin layer（Step 10）
config/    per-board port mapping (*.ini)
tests/     unit tests
logs/      CSV result logs (gitignored)
```

## セットアップ
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## ポートマッピング方針
LAN1..6 → ifname の対応は「ボード機種ごとの定数」。config/*.ini に一度だけ定義し、
CSVは論理LAN番号でIPを持つ。Intel→AMD移行は config ファイルの差し替えのみ。
