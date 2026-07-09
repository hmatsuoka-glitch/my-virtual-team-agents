#!/bin/zsh
# 普段使いのChromeを「リモート接続を受け付ける状態」で起動する（CDPモード用）。
# ボットはこのChromeに後から接続するため、Xのbot検出を受けにくく、ログイン作業も不要。
#
# 使い方: 一度Chromeを完全終了してから、これを実行する
#   osascript -e 'quit app "Google Chrome"'; sleep 2; zsh pilot-company/browser/start_chrome_cdp.sh
#
# 注意: このウィンドウでXにログイン済みであること（普段のプロファイルがそのまま使われる）。

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT=9222

if [ ! -x "$CHROME" ]; then
  echo "Google Chrome が見つかりません: $CHROME"
  echo "Chromeをインストールするか、パスを確認してください。"
  exit 1
fi

# 普段のプロファイル（Default）をそのまま使い、リモートデバッグを有効化して起動
"$CHROME" --remote-debugging-port=$PORT \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome" \
  --profile-directory="Default" \
  --restore-last-session >/dev/null 2>&1 &

echo "ChromeをCDP有効（ポート $PORT）で起動しました。"
echo "このChromeでXにログイン済みか確認してください。"
echo "ボット側で環境変数 X_BOT_CDP=http://localhost:$PORT を設定すると接続します。"
