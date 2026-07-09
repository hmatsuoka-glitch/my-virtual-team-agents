#!/bin/zsh
# ボット専用のChromeプロファイルを「リモート接続を受け付ける状態」で起動する（CDPモード用）。
# ボットはこのChromeに後から接続するため、Xのbot検出を受けにくく、ログイン作業も1回だけで済む。
#
# 重要: Chrome 136以降はセキュリティ上、"デフォルトのプロファイル"ではリモートデバッグが
#       無効化される。そのため専用プロファイル ~/.x-bot-chrome を使う（本物のGoogle Chrome）。
#
# 使い方:  zsh pilot-company/browser/start_chrome_cdp.sh
# 初回のみ: 開いたChromeで x.com を開き、いつも通りXにログインする（以降は保持される）。

PORT=9222
DATADIR="$HOME/.x-bot-chrome"

if [ ! -d "/Applications/Google Chrome.app" ]; then
  echo "Google Chrome が見つかりません: /Applications/Google Chrome.app"
  exit 1
fi

# すでに起動済み（ポートが応答する）なら何もしない（launchdから毎回呼んでも安全）
if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  echo "CDP対応Chromeは既に起動しています（ポート $PORT）。"
  exit 0
fi

# open -na で macOS の LaunchServices 経由の新規インスタンスとして起動する。
# これによりターミナル終了時のHUPで巻き添え終了しない（バックグラウンド&だと死ぬ）。
open -na "Google Chrome" --args \
  --remote-debugging-port=$PORT \
  --user-data-dir="$DATADIR" \
  --no-first-run --no-default-browser-check

# ポートが開くまで最大10秒待つ
for i in {1..20}; do
  sleep 0.5
  if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "CDP対応Chromeを起動しました（ポート $PORT・専用プロファイル $DATADIR）。"
    echo "初回のみ: このChromeで x.com を開いてXにログインしてください。"
    exit 0
  fi
done

echo "起動はしましたが、ポート $PORT の応答を確認できませんでした。"
echo "開いたChromeウィンドウを確認してください。"
