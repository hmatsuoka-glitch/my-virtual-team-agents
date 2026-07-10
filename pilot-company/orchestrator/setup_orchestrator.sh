#!/bin/zsh
# 案A: Mac一元化オーケストレーターのセットアップ（Mac用）
# 生成もMacで行い、Macのgitでpushする（クラウド無人セッションの403を回避）。
#
# 前提: リポジトリは ~/my-virtual-team-agents、ブランチ main。X投稿ボット(launchd)は設定済み。
# 使い方: cd ~/my-virtual-team-agents && zsh pilot-company/orchestrator/setup_orchestrator.sh
set -e

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LA="$HOME/Library/LaunchAgents"
echo "==> リポジトリ: $REPO"

# --- 1) Claude CLI の確認/導入 ---
if command -v claude >/dev/null 2>&1; then
  echo "==> Claude CLI: 導入済み ($(command -v claude))"
else
  echo "==> Claude CLI が未導入です。npm でインストールします..."
  if command -v npm >/dev/null 2>&1; then
    npm install -g @anthropic-ai/claude-code
  else
    echo "!! npm が見つかりません。Node.js を https://nodejs.org からインストールして再実行してください。"
    exit 1
  fi
fi

# --- 2) 生成ジョブ(launchd)を4本登録 ---
mkdir -p "$LA"
write_job() {
  local label="$1" hour="$2" min="$3" weekday="$4" prompt="$5"
  # weekday: "*"=毎平日は Weekday指定せず月〜金を個別化できないためStartCalendarIntervalを平日分並べる。
  # ここでは簡易に「毎日 hour:min」で登録し、土日は prompt 側/運用で無視（コスト最小化したい場合は要調整）。
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
    <string>cd ${REPO} &amp;&amp; git checkout main &amp;&amp; git pull --rebase &amp;&amp; claude -p "\$(cat ${prompt})" --dangerously-skip-permissions 2&gt;&amp;1</string>
  </array>
EOF
  if [ -n "$weekday" ]; then
    cat >> "$LA/${label}.plist" <<EOF
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${min}</integer><key>Weekday</key><integer>${weekday}</integer></dict>
EOF
  else
    # 平日(月〜金)に発火させるため Weekday 1..5 を配列で指定
    cat >> "$LA/${label}.plist" <<EOF
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${min}</integer><key>Weekday</key><integer>1</integer></dict>
    <dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${min}</integer><key>Weekday</key><integer>2</integer></dict>
    <dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${min}</integer><key>Weekday</key><integer>3</integer></dict>
    <dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${min}</integer><key>Weekday</key><integer>4</integer></dict>
    <dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${min}</integer><key>Weekday</key><integer>5</integer></dict>
  </array>
EOF
  fi
  cat >> "$LA/${label}.plist" <<EOF
  <key>StandardOutPath</key><string>/tmp/${label}.log</string>
  <key>StandardErrorPath</key><string>/tmp/${label}.log</string>
</dict>
</plist>
EOF
  launchctl unload "$LA/${label}.plist" 2>/dev/null || true
  launchctl load "$LA/${label}.plist"
  echo "    ${label} を登録しました（${hour}:${min}）"
}

# 平日: 朝会9:00 / 昼会13:00 / 終業17:30。X投稿ボット(9:30/13:30)より前に生成が回るよう配置。
write_job com.let.ai-company.morning  9  0 "" "pilot-company/prompts/morning.md"
write_job com.let.ai-company.midday   13 0 "" "pilot-company/prompts/midday.md"
write_job com.let.ai-company.closing  17 30 "" "pilot-company/prompts/closing.md"
# 週次: 金曜(Weekday=5)16:00
write_job com.let.ai-company.weekly   16 0 5 "pilot-company/prompts/weekly-review.md"

echo ""
echo "==> 登録完了。残りの手動ステップ:"
echo ""
echo "  1) Claude CLI にログイン（初回のみ・あなたのClaudeサブスクでOK）:"
echo "       claude            # 起動して指示に従いログイン。/exit で抜ける"
echo ""
echo "  2) ヘッドレス動作テスト（実際に朝会を1回手動実行）:"
echo "       cd ${REPO} && claude -p \"\$(cat pilot-company/prompts/morning.md)\" --dangerously-skip-permissions"
echo "       → pilot-company/ にコミットが積まれ、git push まで通れば成功"
echo ""
echo "  3) 登録確認: launchctl list | grep ai-company"
echo ""
echo "  停止: launchctl unload ~/Library/LaunchAgents/com.let.ai-company.*.plist"
echo ""
echo "  ※ Mac は平日9〜18時スリープさせない（設定済み）。電源接続・フタは開けたまま。"
