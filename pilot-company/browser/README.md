# ローカルXボット セットアップガイド（X API移行までの暫定運用）

ログイン済みChromeプロファイルを自動操作してXへの投稿・成果取得を行う。
**あなたのMac上で動く**（クラウドRoutinesはローカルブラウザに触れないため）。

> ⚠️ この方式はXの自動化ルール（自動化はAPI経由）に沿わない暫定運用であり、
> アカウント制限のリスクがある（2026-07-08 HARU了承済み）。
> リスク低減のため「1日2件・人間らしい入力速度・ランダム待機」を実装済み。
> **X APIキーを環境変数に設定した時点で、クラウド側がAPI投稿に自動で切り替わる。**
> その際はこのボットの launchd を unload して退役させること。

## 2つの接続モード

Xは「自動化ブラウザからのログイン」をbot検出で弾くことがある（実際に
「お使いのアカウントへのログインが現在許可されていません」エラーが確認された）。
これを避けるため、**普段使いのChromeに後から接続するCDPモードを推奨**する。

| モード | 仕組み | bot検出 | ログイン作業 |
|--------|--------|---------|------------|
| CDPモード（推奨） | 普段のChromeを特殊起動し、ボットが接続 | されにくい（本物のブラウザ） | 不要（ログイン済みを使う） |
| プロファイルモード | 専用の自動化ブラウザを開く | されやすい | 必要（弾かれる場合あり） |

## セットアップ（1回だけ・約15分）

### 共通: Python環境の用意

```bash
cd ~/my-virtual-team-agents
zsh pilot-company/browser/setup_local.sh   # venv作成・Playwright導入・launchd 3本登録
```
（macOSのHomebrew PythonはPEP 668でpip直接インストール禁止のため、専用venv ~/.x-bot-venv に隔離）

### CDPモード（推奨）

```bash
# 1. Chromeを完全終了 → CDP有効で再起動（普段のプロファイル・ログイン状態を使う）
osascript -e 'quit app "Google Chrome"'; sleep 2
zsh pilot-company/browser/start_chrome_cdp.sh
#    → 開いたChromeで x.com を開き、ログイン済みか確認する

# 2. 環境変数でCDP接続を有効化して動作確認（投稿しない）
export X_BOT_CDP=http://localhost:9222
echo 'テスト投稿です' > pilot-company/tasks/x_queue/test.txt
~/.x-bot-venv/bin/python pilot-company/browser/x_browser_bot.py post --dry-run
rm pilot-company/tasks/x_queue/test.txt

# 3. 初回だけ有人で本番投稿を1回見届ける（キューに実ドラフトが入ってから）
~/.x-bot-venv/bin/python pilot-company/browser/x_browser_bot.py post
```

CDPモードをlaunchdで常用する場合は、各plistの起動コマンド先頭で
`start_chrome_cdp.sh` を呼び、環境変数 `X_BOT_CDP` を設定する（setup_local.sh がCDP対応版を生成）。

### プロファイルモード（CDPが使えない時のフォールバック）

```bash
~/.x-bot-venv/bin/python pilot-company/browser/x_browser_bot.py login   # Xにログイン
echo 'テスト投稿です' > pilot-company/tasks/x_queue/test.txt
~/.x-bot-venv/bin/python pilot-company/browser/x_browser_bot.py post --dry-run
rm pilot-company/tasks/x_queue/test.txt
```
※このモードは冒頭のbot検出エラーが出る可能性がある。出たらCDPモードに切り替えること。

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
