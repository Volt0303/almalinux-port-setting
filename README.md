# 6ポートLAN IPアドレス自動設定・照合システム

AlmaLinux 9.8 搭載産業用PC（約400台）の6ポートLANへ、支給CSV/Excelを元に
IPv4固定設定を自動適用し、実適用値を読み戻して照合、結果をCSVログに記録するツール。

- **発注**: 城迫 様（エフアンドエフ(株)）　　**受注**: ユキソフト
- **対象OS**: AlmaLinux 9.7 / 9.8（Python 3.9, NetworkManager / nmcli）
- **対象HW**: ASRock IMB-A8000M（AMD Ryzen Embedded PRO 8840U）+ Intel I350-T4V2
  （オンボード2ポート + 増設4ポート = 計6ポート）
- **規模**: 約400台 × 6ポート = 約2,400ポート

---

## 目次
1. [機能](#機能)
2. [動作の仕組み](#動作の仕組み)
3. [ディレクトリ構成](#ディレクトリ構成)
4. [開発環境のセットアップ](#開発環境のセットアップ)
5. [実行ファイルのビルド](#実行ファイルのビルド)
6. [新しい実機への導入手順](#新しい実機への導入手順)
7. [使い方（GUI）](#使い方gui)
8. [使い方（CLI）](#使い方cli)
9. [支給ファイル（CSV / Excel）の形式](#支給ファイルcsv--excelの形式)
10. [ポートマッピング（config/*.ini）](#ポートマッピングconfigini)
11. [ログ](#ログ)
12. [テスト](#テスト)
13. [トラブルシューティング](#トラブルシューティング)
14. [Intel → AMD 移行（Phase 2）](#intel--amd-移行phase-2)
15. [納品物・検収](#納品物検収)

---

## 機能
- 顧客支給の **CSV / Excel** を読み込み、シリアル番号ごとの設定を取得
- 6ポートへ **IPv4固定設定**（IP / サブネット / 任意でゲートウェイ・DNS）を自動適用
- 適用後に **実際の値を読み戻して照合**（照合＝compare）し、OK / NG を判定
- 結果を **CSVログ**（Excel対応・追記式）に保存（トレーサビリティ）
- **GUI**（現場作業者向け）と **CLI**（SSH・自動化向け）の両対応
- **ドライラン**（既定）で実行内容を事前確認、ネットワークを変更しない
- ポート単位の失敗を隔離（1ポート失敗しても残りは継続）
- シリアル番号の **自動判別**（`dmidecode`）

---

## 動作の仕組み

処理の流れ（CLI・GUIとも同一のコアを呼ぶ）:

```
支給ファイル ─▶ loader ─▶ netmask ─▶ applier ─▶ reader ─▶ compare ─▶ logwriter
  (CSV/xlsx)     読込      正規化      nmcli適用   読み戻し   照合       CSVログ
```

- **ドライラン**: `applier` は実行する nmcli コマンドを組み立てるだけで実行しない。
- **本適用（commit）**: 実際に適用 → `reader` で `ip addr` / `nmcli` から実値を取得 →
  `compare` で期待値と照合 → `logwriter` でCSVに追記。

コアロジックは OS 非依存のため Ubuntu 開発機で単体テスト可能。nmcli を叩く部分
（applier / reader）は AlmaLinux 実機で検証する（開発機では dry-run のみ）。

---

## ディレクトリ構成

```
Linux-port-setting/
├─ ipset/
│  ├─ core/
│  │  ├─ loader.py       支給CSV/xlsx の読込・正規化・検証
│  │  ├─ netmask.py      IPv4検証・netmask⇔CIDR変換
│  │  ├─ applier.py      nmcli による適用（dry-run対応）
│  │  ├─ reader.py       実適用値の読み戻し
│  │  ├─ compare.py      期待値 vs 実値 の照合
│  │  ├─ logwriter.py    CSVログ追記（UTF-8 BOM）
│  │  └─ pipeline.py     CLI/GUI共通のオーケストレーション
│  ├─ cli.py             ヘッドレス実行（SSH/自動化）
│  └─ gui.py             Tkinter GUI（現場作業者向け）
├─ tools/
│  └─ inventory.py       物理ポート ⇔ ifname 対応表の生成補助
├─ config/
│  ├─ config_intel.ini.example   雛形（コピーして実名を記入）
│  ├─ config_intel.ini           Intel検証機の実マッピング（gitignore）
│  └─ config_amd.ini             AMD量産機の実マッピング（Phase 2）
├─ tests/                unittest（stdlibのみ・pytest不要）
├─ logs/                 CSV結果ログ（gitignore）
├─ docs/
│  ├─ 操作マニュアル.md          現場作業者向け操作手順
│  └─ 検収チェックリスト.md       受入基準（仕様書16章）
├─ run_cli.py / run_gui.py       PyInstaller エントリポイント
├─ build.sh                      dist/ に単一実行ファイルを生成
├─ launch_gui.sh                 GUI起動ラッパ（sudo/表示/作業ディレクトリを処理）
├─ setup_desktop.sh              実機へインストールしデスクトップ登録
├─ requirements.txt
└─ README.md
```

---

## 開発環境のセットアップ

Ubuntu 開発機（VPS）でのコア開発・単体テスト用。

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt      # openpyxl（xlsx読込）。CSVはstdlibのみで動作
```

> CSV / INI / tkinter は標準ライブラリのみで動作します。`openpyxl` は
> Excel(.xlsx) を読む場合にのみ必要です。

---

## 実行ファイルのビルド

配布用の単一実行ファイルは **必ず AlmaLinux 実機上で** ビルドします
（PyInstaller はホストの glibc / tkinter を同梱するため、実行環境と一致させる必要あり）。

```bash
sudo dnf install -y python3 python3-tkinter
bash build.sh
```

生成物（`dist/`）:

| ファイル | 内容 |
|---|---|
| `dist/ipset-gui`      | GUI 実行ファイル（単体・Python不要） |
| `dist/ipset-cli`      | CLI 実行ファイル（単体・Python不要） |
| `dist/launch_gui.sh`  | GUI起動ラッパ |
| `dist/config/`        | ポートマッピングINI |
| `dist/logs/`          | ログ出力先 |
| `dist/操作マニュアル.md` | 操作マニュアル |

---

## 新しい実機への導入手順

新しい AlmaLinux 機へ導入する際の、最初から最後までの手順。
**最重要ポイントは手順3（ポートマッピング）** です。ポート名は機種ごとに異なります。

### 1. ファイルを配置
プロジェクト一式（または `dist/` と各スクリプト）を USB / `scp` で対象機へコピー。

### 2. GUI用の依存パッケージを導入
```bash
sudo dnf install -y python3-tkinter google-noto-sans-cjk-jp-fonts
```
> **日本語フォントは必須**です。未導入だと GUI のラベルが □□□（豆腐）になります。
> minimal インストールの実機では入っていないため、必ず導入してください。

### 3. ⚠️ ポートマッピングを設定（最重要）
物理ポート LAN1〜6 と OS のインターフェース名（ifname）の対応を確認します。
```bash
python3 tools/inventory.py
```
出力を物理ラベルに合わせ、`config/config_intel.ini`（AMD機なら `config_amd.ini`）へ保存。
どのポートがどれか不明な場合は LED を点滅させて確認:
```bash
sudo ethtool -p <ifname> 10
```
> 現行機と **同一ハードウェア** なら既存の `config_intel.ini` をそのまま流用可。

### 4. ビルド（未ビルドの場合）
```bash
bash build.sh
```

### 5. インストールとデスクトップ登録
```bash
sudo bash setup_desktop.sh
```
これにより次が行われます:
- `dist/` 一式を `/opt/ipset/` へインストール
- この実行ファイルに限り **パスワードなし sudo** を許可（`/etc/sudoers.d/ipset`）
- アプリケーションメニューとデスクトップに **「LAN IP設定ツール」** を登録
  （デスクトップフォルダはロケール自動判定：`Desktop` / `デスクトップ`）

### 6. 起動（初回のみ許可操作が必要な場合あり）
- **アプリケーションメニュー（推奨）**: Super（Windows）キー → `LAN` と入力 → クリック
- **デスクトップアイコン**: 右クリック →「起動を許可する」→ ダブルクリック

---

## 使い方（GUI）

1. ツールを起動（上記手順6）。
2. **［参照...］** で支給ファイル（CSV / Excel）を選択。
3. **対象シリアル** を選択（自動判別されない場合のみ手動）。
4. 中央に **設定内容（期待値）** が LAN1〜6 分表示される。内容を確認。
5. まず **「ドライラン（変更しない）」に✓を入れたまま**［設定開始］→ 実行内容を確認。
6. 問題なければ **✓を外して**［設定開始］→ 確認ダイアログで「はい」。
7. **設定結果** に各ポートの判定（**緑=OK / 赤=NG**）が表示される。
8. 画面下部に **PASS / FAIL とログ保存先** が表示される。

---

## 使い方（CLI）

```bash
# ファイル内のシリアル一覧を表示
python3 -m ipset.cli 支給ファイル.csv --list

# 内容確認のみ（ドライラン・既定。ネットワークを変更しない）
python3 -m ipset.cli 支給ファイル.csv --serial F30126E001

# 実際に適用・読み戻し・照合・ログ記録（管理者権限が必要）
sudo python3 -m ipset.cli 支給ファイル.csv --serial F30126E001 --commit
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--serial <SN>` | 対象シリアル（省略時は `dmidecode` で自動判別、単一機なら自動選択） |
| `--commit`      | 実際に適用（既定はドライラン） |
| `--config <path>` | ポートマッピングINI（既定 `config/config_intel.ini`） |
| `--log <path>`  | CSVログの保存先（既定 `logs/result.csv`） |
| `--list`        | シリアル一覧を表示して終了 |

終了コード: `0 = 全ポートOK` / `1 = NGあり・読込エラー` / `2 = 使用方法エラー`

---

## 支給ファイル（CSV / Excel）の形式

1ポート1行（ロング形式）。ヘッダ名は別名・大文字小文字・全角を吸収します。

| 列 | 必須 | 例 | 別名の例 |
|---|:--:|---|---|
| `SN`         | ○ | F30126E001 | serial, シリアル |
| `con_name`   | ○ | LAN1 | lan, port, connection |
| `ip_address` | ○ | 192.168.1.100 | ip, address |
| `subnet`     | ○ | 255.255.255.0 | netmask, mask, prefix |
| `ifname`     | − | enp3s0 | interface, dev |
| `gateway`    | − | 192.168.1.1 | gw |
| `dns`        | − | 8.8.8.8 | nameserver |

例（`IPsetting_sample.csv`）:
```
SN,ifname,con_name,ip_address,subnet,gateway,dns
F30126E001,enp3s0,LAN1,192.168.1.100,255.255.255.0,,
```

- サブネットは `255.255.255.0` / `24` / `/24` のいずれも可（内部で CIDR へ変換）。
- ゲートウェイ・DNS は空欄可（空欄の項目は照合対象から除外）。
- 同一機内でIPが重複していると **警告**（エラーではない）を表示。

---

## ポートマッピング（config/*.ini）

LAN1〜6 と ifname の対応は「ボード機種ごとの定数」。config に一度だけ定義し、
支給CSVは論理LAN番号でIPを持ちます。ifname は config を優先し、CSVの ifname は
照合のみ（食い違えば警告）。

```ini
[board]
name = INTEL-DEV
description = Intel development machine

[port_map]
LAN1 = enp3s0     # オンボード1
LAN2 = enp4s0     # オンボード2
LAN3 = enp1s0f3   # I350-T4V2（ブラケット並び f3→f0）
LAN4 = enp1s0f2
LAN5 = enp1s0f1
LAN6 = enp1s0f0
```

`config/config_intel.ini` は機種固有のため **gitignore** 対象。雛形
`config_intel.ini.example` をコピーして実名を記入してください。

---

## ログ

- 実行結果は **`logs/result.csv`**（GUI/CLIとも既定）に **追記** 保存。
- UTF-8 BOM 付きのため Excel でそのまま開けます。
- 列: `datetime, serial, lan, ip, subnet, gateway, dns, actual, result, error`
- 検査記録（トレーサビリティ）として保管してください。

---

## テスト

標準ライブラリの `unittest` のみ（pytest 不要）。

```bash
python3 -m unittest discover -s tests
```

- コアロジック（loader / netmask / applier / reader / compare / logwriter）は
  ランナー注入により実ネットワーク無しで検証。
- 開発機（tkinter 無し）でも `gui.py` 以外はテスト可能。

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| GUIラベルが □□□ | 日本語フォント未導入 | `sudo dnf install -y google-noto-sans-cjk-jp-fonts` |
| ダブルクリックで無反応・カーソルが回るだけ | `sudo` が DISPLAY を落とす／GNOMEの起動許可 | `launch_gui.sh` 経由で起動（DISPLAY転送＋ログ出力）。アイコンは右クリック→「起動を許可する」 |
| 「設定ファイルが見つかりません config/config_intel.ini」 | 作業ディレクトリが `/` | `launch_gui.sh` が `cd /opt/ipset` を実行（同梱済み）。CLIは config のあるフォルダで実行 |
| デスクトップにアイコンが出ない | 日本語ロケールで `デスクトップ` フォルダ | `setup_desktop.sh` がロケール自動判定（`xdg-user-dir DESKTOP`） |
| GUIが起動しない（原因不明） | — | `cat /tmp/ipset-gui.log` に起動ログとエラーが出力される |
| `ModuleNotFoundError: tkinter` | tkinter 未導入 | `sudo dnf install -y python3-tkinter` |
| パスワードを毎回聞かれる | sudoers 未設定 | `setup_desktop.sh` が対象実行ファイルのみ NOPASSWD を設定 |

> **注意（リモート作業時）**: AnyDesk 接続を保持しているインターフェース
> （例: `enp3s0` 192.168.1.41/24）に対して `--commit` を実行すると接続が切れます。
> リモート検証では該当ポートを除いた支給ファイルを使用してください。

---

## Intel → AMD 移行（Phase 2）

コード変更は不要。移行作業の本体は **config ファイルの差し替え** です。

1. Intel検証機の SSD を AMD実機へ移設。
2. AMD実機で `python3 tools/inventory.py` を再実行し ifname を確認。
3. 差分を `config/config_amd.ini` に反映（`--config` で指定、またはGUIのINI欄で選択）。
4. `nmcli device status` で全6ポートの認識を確認。
5. 検収チェックリスト B項（1〜7）を再実施。

詳細は `docs/検収チェックリスト.md` を参照。

---

## 納品物・検収

- 納品物: Pythonソース一式 / 実行プログラム（`dist/`）/ config / 操作マニュアル
- 受入基準: `docs/検収チェックリスト.md`（仕様書16章）
- 操作手順: `docs/操作マニュアル.md`
