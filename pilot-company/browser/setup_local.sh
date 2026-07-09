#!/bin/zsh
# ローカルXボットの一括セットアップスクリプト（Mac用）
# 使い方: cd ~/my-virtual-team-agents && zsh pilot-company/browser/setup_local.sh
# やること: ①Playwrightインストール ②launchdジョブ3本の作成と登録 ③残りの手動手順の案内
set -e

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LA="$HOME/Library/LaunchAgents"
echo "==> リポジトリ: $REPO"

echo "==> 1/3 Playwright をインストールしています..."
pip3 install playwright
python3 -m playwright install chromium

echo "==> 2/3 launchd ジョブを3本登録しています..."
mkdir -p "$LA"

write_plist() {
  local label="$1" hour="$2" min="$3" sub="$4"
  cat > "$LA/${label}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd ${REPO} &amp;&amp; git pull --rebase &amp;&amp; python3 pilot-company/browser/x_browser_bot.py ${sub} &amp;&amp; git add pilot-company &amp;&amp; git commit -m "x-bot: ${sub}" &amp;&amp; git push || true</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${min}</integer></dict>
  <key>StandardOutPath</key><string>/tmp/${label}.log</string>
  <key>StandardErrorPath</key><string>/tmp/${label}.log</string>
</dict>
</plist>
EOF
  launchctl unload "$LA/${label}.plist" 2>/dev/null || true
  launchctl load "$LA/${label}.plist"
  echo "    ${label}（毎日 ${hour}:${min}）を登録しました"
}

write_plist com.let.x-bot.post-am 9 30 post
write_plist com.let.x-bot.post-pm 13 30 post
write_plist com.let.x-bot.metrics 17 10 metrics

echo ""
echo "==> 3/3 自動セットアップ完了！残りの手動ステップ:"
echo ""
echo "  1) Xへログイン（初回のみ）:"
echo "       python3 pilot-company/browser/x_browser_bot.py login"
echo ""
echo "  2) 動作確認（実際には投稿されません）:"
echo "       echo 'テスト投稿です' > pilot-company/tasks/x_queue/test.txt"
echo "       python3 pilot-company/browser/x_browser_bot.py post --dry-run"
echo "       rm pilot-company/tasks/x_queue/test.txt"
echo ""
echo "  3) Macのスリープ設定（9〜18時に寝かせない）: HARU_MANUAL.md 参照"
echo ""
echo "  停止したいとき: launchctl unload ~/Library/LaunchAgents/com.let.x-bot.*.plist"
