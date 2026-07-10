#!/bin/zsh
# note自動投稿ボットの launchd 登録（Mac用）。X bot と同じ CDP Chrome を使う。
# 使い方: cd ~/my-virtual-team-agents && zsh pilot-company/browser/setup_note.sh
# 前提: setup_local.sh 実行済み（venv・start_chrome_cdp.sh がある）。CDP Chrome で note にログイン済み。
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LA="$HOME/Library/LaunchAgents"
PY="$HOME/.x-bot-venv/bin/python"
mkdir -p "$LA"

label=com.let.note-bot.publish
cat > "$LA/${label}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd ${REPO} &amp;&amp; zsh pilot-company/browser/start_chrome_cdp.sh &amp;&amp; sleep 5 &amp;&amp; export X_BOT_CDP=http://127.0.0.1:9222 &amp;&amp; git pull --rebase &amp;&amp; ${PY} pilot-company/browser/note_bot.py publish &amp;&amp; git add pilot-company &amp;&amp; git commit -m "note-bot: publish" &amp;&amp; git pull --rebase &amp;&amp; git push || true</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer><key>Weekday</key><integer>1</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer><key>Weekday</key><integer>3</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer><key>Weekday</key><integer>5</integer></dict>
  </array>
  <key>StandardOutPath</key><string>/tmp/${label}.log</string>
  <key>StandardErrorPath</key><string>/tmp/${label}.log</string>
</dict>
</plist>
EOF
launchctl unload "$LA/${label}.plist" 2>/dev/null || true
launchctl load "$LA/${label}.plist"
echo "==> ${label} を登録しました（月・水・金 10:30 に note_queue の記事を1本公開）"
echo ""
echo "残りの手動ステップ:"
echo "  1) CDP Chrome で note にログイン（初回のみ）:"
echo "       zsh pilot-company/browser/start_chrome_cdp.sh   # 開いたChromeで note.com にログイン"
echo "  2) 動作確認（公開せず・入力までを確認）:"
echo "       export X_BOT_CDP=http://127.0.0.1:9222"
echo "       ~/.x-bot-venv/bin/python pilot-company/browser/note_bot.py publish --dry-run"
echo "       → 開いたChromeでタイトル・本文が入力され、browser/logs にスクショが出れば成功"
echo "  3) 初回だけ有人で本番公開を見届ける:"
echo "       ~/.x-bot-venv/bin/python pilot-company/browser/note_bot.py publish"
echo ""
echo "  停止: launchctl unload ~/Library/LaunchAgents/com.let.note-bot.*.plist"
