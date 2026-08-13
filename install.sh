#!/usr/bin/env bash
# ============================================================================
#  6ポートLAN IP設定ツール  かんたんインストーラ
# ============================================================================
#  使い方（端末に貼り付けて実行）:
#      bash install.sh
#
#  この1コマンドで、下記をまとめて実行します。
#      1. 必要なパッケージの導入（日本語フォント等）
#      2. ポート設定ファイルの確認
#      3. ビルド（実行ファイルの作成）
#      4. インストール（アイコン登録）
#
#  ※ sudo は付けずに実行してください（途中でパスワードを聞かれます）。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 画面表示用（端末以外へ出力する場合は色を付けない） ----------------------
if [ -t 1 ]; then
    BOLD=$(tput bold 2>/dev/null || true)
    RESET=$(tput sgr0 2>/dev/null || true)
    GREEN=$(tput setaf 2 2>/dev/null || true)
    RED=$(tput setaf 1 2>/dev/null || true)
    YELLOW=$(tput setaf 3 2>/dev/null || true)
else
    BOLD=""; RESET=""; GREEN=""; RED=""; YELLOW=""
fi

step()  { echo ""; echo "${BOLD}=== $* ===${RESET}"; }
ok()    { echo "${GREEN}  [OK]${RESET} $*"; }
warn()  { echo "${YELLOW}  [注意]${RESET} $*"; }
fail()  { echo "${RED}  [エラー]${RESET} $*"; }

die() {
    echo ""
    fail "$1"
    echo ""
    echo "  この画面の内容をコピーして、担当者へご連絡ください。"
    echo ""
    exit 1
}

# ---- 0. 事前チェック --------------------------------------------------------
step "0/5  環境を確認しています"

if [ "$(id -u)" -eq 0 ]; then
    die "sudo を付けずに実行してください（正しい実行方法:  bash install.sh ）"
fi

if [ ! -f "$SCRIPT_DIR/build.sh" ] || [ ! -d "$SCRIPT_DIR/ipset" ]; then
    die "ツールのフォルダ内で実行してください。
         例:  cd ~/PortSetting/almalinux-port-setting
              bash install.sh"
fi
ok "作業フォルダ: $SCRIPT_DIR"

command -v python3 >/dev/null 2>&1 || die "python3 が見つかりません。"
ok "Python: $(python3 --version 2>&1)"

# 起動中のツールがあると上書きできないため、先に知らせる
if pgrep -f "/opt/ipset/ipset-gui" >/dev/null 2>&1; then
    warn "ツール（LAN IP設定ツール）が起動中です。"
    echo "       ${BOLD}先にツールの画面を閉じてから続行してください。${RESET}"
    echo "       （閉じずに続行してもインストールは行えますが、"
    echo "         新しい版を使うには開き直しが必要です。）"
fi

echo ""
echo "  これからインストールを開始します。"
echo "  途中でパスワードの入力を求められます（ログイン時のパスワード）。"
echo ""
read -r -p "  続行しますか？ [Enter=はい / Ctrl+C=中止] " _ || true

# ---- 1. パッケージ導入 ------------------------------------------------------
step "1/5  必要なパッケージを導入しています（数分かかります）"
echo "  ・日本語フォント（画面の文字化け防止）"
echo "  ・ビルドに必要な Python 一式"
echo ""

if sudo dnf install -y \
        google-noto-sans-cjk-jp-fonts \
        python3 python3-pip python3-tkinter 2>&1 | tail -5; then
    ok "パッケージの導入が完了しました"
else
    die "パッケージの導入に失敗しました。インターネット接続をご確認ください。"
fi

# ---- 2. ポート設定の確認 ----------------------------------------------------
step "2/5  ポート設定ファイルを確認しています"

DETECT_OUT=$(python3 - <<'PY' 2>/dev/null
try:
    from ipset.core import detect
    ranked = detect.evaluate_configs('config')
    if not ranked:
        print("NONE")
    else:
        best = ranked[0]
        status = "PERFECT" if best.perfect else "PARTIAL"
        print("%s|%s|%d|%d|%s" % (status, best.path, best.matched, best.total,
                                  ",".join(best.missing)))
except Exception as e:
    print("ERROR|%s" % e)
PY
)

CONFIG_OK=0
case "$DETECT_OUT" in
    PERFECT*)
        IFS='|' read -r _ cfgpath matched total _ <<< "$DETECT_OUT"
        ok "この機体に対応する設定が見つかりました: $(basename "$cfgpath") ($matched/$total ポート一致)"
        CONFIG_OK=1
        ;;
    PARTIAL*)
        IFS='|' read -r _ cfgpath matched total missing <<< "$DETECT_OUT"
        warn "この機体に完全一致する設定ファイルがありません。"
        echo "       もっとも近い候補: $(basename "$cfgpath") ($matched/$total ポート一致)"
        echo "       見つからないポート: $missing"
        ;;
    NONE*)
        warn "設定ファイル（config/*.ini）がありません。"
        ;;
    *)
        warn "設定の確認をスキップしました。"
        ;;
esac

if [ "$CONFIG_OK" -eq 0 ]; then
    echo ""
    echo "  ${BOLD}このままインストールは続行できます${RESET}が、使用前に"
    echo "  ポート対応表の作成が必要です。"
    echo "  → 『インストール手順書.md』の 手順3・手順4 をご覧ください。"
    echo ""
    read -r -p "  続行しますか？ [Enter=はい / Ctrl+C=中止] " _ || true
fi

# ---- 3. ビルド --------------------------------------------------------------
step "3/5  実行ファイルを作成しています（数分かかります）"
echo "  ※ たくさんの文字が流れますが、正常な動作です。"
echo ""

if bash build.sh > /tmp/ipset-build.log 2>&1; then
    ok "作成が完了しました"
    if [ -x dist/ipset-gui ]; then
        ok "GUI 実行ファイル: dist/ipset-gui"
    fi
    if [ -x dist/ipset-cli ]; then
        ok "CLI 実行ファイル: dist/ipset-cli"
    fi
    echo "  （詳しい記録: /tmp/ipset-build.log）"
else
    echo ""
    tail -20 /tmp/ipset-build.log
    die "作成に失敗しました。詳細は /tmp/ipset-build.log をご確認ください。"
fi

# ---- 4. インストール --------------------------------------------------------
step "4/5  PCにインストールしています"

if sudo bash setup_desktop.sh; then
    ok "インストールが完了しました"
else
    die "インストールに失敗しました。"
fi

# ---- 5. 完了 ----------------------------------------------------------------
step "5/5  完了"
echo ""
echo "  ${GREEN}${BOLD}インストールが完了しました。${RESET}"
echo ""
echo "  ${BOLD}起動方法${RESET}"
echo "    1. 画面左上の「アクティビティ」をクリック"
echo "    2. 検索窓に  LAN  と入力"
echo "    3.「LAN IP設定ツール」のアイコンをクリック"
echo ""

if [ "$CONFIG_OK" -eq 1 ]; then
    echo "  起動後、画面下部に「ボード自動判別: ...」と表示されれば正常です。"
else
    echo "  ${YELLOW}${BOLD}使用前の作業${RESET}"
    echo "    ポート対応表がまだ作成されていません。"
    echo "    『インストール手順書.md』の 手順3・手順4 を実施してください。"
    echo "    作成後、下記を実行して反映します:"
    echo "        bash build.sh && sudo bash setup_desktop.sh"
fi
echo ""
