# ローカルXボット セットアップガイド（X API移行までの暫定運用）

ログイン済みChromeプロファイルを自動操作してXへの投稿・成果取得を行う。
**あなたのMac上で動く**（クラウドRoutinesはローカルブラウザに触れないため）。

> ⚠️ この方式はXの自動化ルール（自動化はAPI経由）に沿わない暫定運用であり、
> アカウント制限のリスクがある（2026-07-08 HARU了承済み）。
> リスク低減のため「1日2件・人間らしい入力速度・ランダム待機」を実装済み。
> **X APIキーを環境変数に設定した時点で、クラウド側がAPI投稿に自動で切り替わる。**
> その際はこのボットの launchd を unload して退役させること。

## セットアップ（1回だけ・約15分）

```bash
# 1. 依存のインストール
pip3 install playwright
python3 -m playwright install chromium

# 2. Xへログイン（専用プロファイル ~/.x-bot-profile に保存される）
cd ~/my-virtual-team-agents
python3 pilot-company/browser/x_browser_bot.py login

# 3. 動作確認（実際には投稿しない）
#    事前に tasks/x_queue/ にテスト用 .txt を1つ置いてから:
python3 pilot-company/browser/x_browser_bot.py post --dry-run
# → browser/logs/ のスクリーンショットで入力状態を確認する

# 4. 初回だけ有人で本番投稿を1回見届ける
python3 pilot-company/browser/x_browser_bot.py post
```

## launchd 登録（3本）

`~/Library/LaunchAgents/com.let.x-bot.post-am.plist`（9:30 投稿）:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.let.x-bot.post-am</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd ~/my-virtual-team-agents && git pull --rebase && python3 pilot-company/browser/x_browser_bot.py post && git add pilot-company && git commit -m "x-bot: post" && git push || true</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>/tmp/x-bot-post-am.log</string>
  <key>StandardErrorPath</key><string>/tmp/x-bot-post-am.log</string>
</dict>
</plist>
```

同じ形式であと2本:

| Label | 時刻 | コマンド末尾の違い |
|-------|------|------------------|
| com.let.x-bot.post-pm | 13:30 | `post`（同上） |
| com.let.x-bot.metrics | 17:10 | `post` を `metrics` に、commit メッセージを `"x-bot: metrics"` に |

登録: `launchctl load ~/Library/LaunchAgents/com.let.x-bot.*.plist`

> 時刻の意図: クラウド朝会(9:00台)がドラフトをキューに積む→9:30に投稿。
> 昼会(13:00台)→13:30に投稿。17:10に成果取得→17:30のクラウド終業が分析に使う。
> **Macは9:00〜18:00スリープさせないこと**（システム設定→ディスプレイオフでもスリープしない設定、または `caffeinate`）。

## 運用中の確認・停止

- 投稿記録: `pilot-company/logs/x_posts.csv`（API方式と共通）
- 失敗時: `pilot-company/browser/logs/*.png` にスクリーンショットが残り、キューは消えない（次回再試行）
- **緊急停止**: `launchctl unload ~/Library/LaunchAgents/com.let.x-bot.*.plist`
- XのUI変更で壊れた場合: スクリーンショットを添えてClaude Codeセッションで修正を依頼

## API方式への移行（推奨される最終形）

1. developer.x.com でキー発行 → claude.ai環境変数に設定（HARU_MANUAL.md 参照）
2. このボットの launchd を unload
3. 以降はクラウドセッションが投稿(post_to_x.py)と成果取得(fetch_x_metrics.py)を実行
