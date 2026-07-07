# 運用マニュアル — 9:00〜18:00 の自律稼働設計

## 基本思想

「常時稼働」ではなく **定時起動（1日3回）＋週次改善会議（金曜）** で就業時間をカバーする。
待機時間にAIを回し続けてもコストが増えるだけなので、人間の会社の「朝会・昼会・終業」に相当するリズムで動かす。

| 時刻 | セッション | プロンプト | 所要 |
|------|-----------|-----------|------|
| 9:00 | 朝会＋制作 | prompts/morning.md | 〜30分 |
| 13:00 | 進捗＋集客 | prompts/midday.md | 〜30分 |
| 17:30 | 終業処理 | prompts/closing.md | 〜15分 |
| 金 16:00 | 週次分析・改善会議 | prompts/weekly-review.md | 〜45分 |

各セッションは冒頭で必ず `memory/strategy.md`（現在の戦略）と `tasks/backlog.md`（タスクキュー）を読んでから動く。
これが「記憶を持った社員が出社する」仕組みの実体。

## スケジューラ設定

> **採用構成（2026-07-07 決定）: ハイブリッド運用**
> - ローカルlaunchd: エージェント定義の同期・auto-commit（従来通り、変更なし）
> - クラウドRoutines: パイロット事業部の定時セッション4本（方法B。登録済み）
> 両者は同じリポジトリにpushするため、各セッションは commit 前に `git pull --rebase` を行う。

### 方法A: ローカルMac（launchd）— 既存の auto-commit 運用の延長

`~/Library/LaunchAgents/com.let.ai-company.morning.plist` の例:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.let.ai-company.morning</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd ~/my-virtual-team-agents && git pull origin main && claude -p "$(cat pilot-company/prompts/morning.md)" --permission-mode acceptEdits</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/ai-company-morning.log</string>
  <key>StandardErrorPath</key><string>/tmp/ai-company-morning.log</string>
</dict>
</plist>
```

同様に midday(13:00) / closing(17:30) / weekly-review(金16:00, `Weekday=5`) を作成し、
`launchctl load ~/Library/LaunchAgents/com.let.ai-company.*.plist` で登録。

### 方法B: Claude Code クラウドセッション + Routines（Macの常時起動が不要）

クラウドセッションで「毎営業日 9:00 / 13:00 / 17:30 にこのリポジトリの prompts/xxx.md を実行する Routine を作って」と依頼すれば、cron トリガーとして登録できる。ローカル同期スクリプトと競合しないよう、クラウド側は **pilot-company/ 配下のみ** を触るルールとする。

## 承認フロー（人間の1日5〜15分）

1. AIが成果物を作ると `tasks/backlog.md` に `[承認待ち]` として登録され、closing セッションが push する
2. HARU はスマホ/PCで backlog を確認し、
   - OK → 自分で公開・販売ボタンを押し、項目を `[公開済み]` に書き換えて commit（または朝会AIに「承認済み」とだけ伝える）
   - NG → 項目に修正コメントを1行書く。翌朝会で haruto が差し戻し処理
3. 売上発生時は `ledger/sales.csv` に1行追記（Phase 2 で Stripe/note からの自動取込に移行）

## データ基盤の成長プラン（現状ゼロ→段階的に自動化）

| Phase | 帳簿 | 集客データ | 売上データ |
|-------|------|-----------|-----------|
| 1（現在） | リポジトリ内CSV（このディレクトリ） | 各媒体の管理画面をAIが読めないため、週1で人間がスクショ or 数値貼り付け | 人間が手動追記 |
| 2 | Google Sheets へ移行（AIがコネクタで直接読み書き） | X/Instagram/GA4 のコネクタ経由で自動取得 | Stripe コネクタ or note売上のSheets転記で半自動 |
| 3 | freee等の会計連携、KPIダッシュボード（kpi/dat 起用） | 同左＋広告データ | 完全自動 |

## 障害時・暴走時の停止方法

- launchd: `launchctl unload ~/Library/LaunchAgents/com.let.ai-company.*.plist`
- Routines: セッションで「Routineを全部止めて」と指示
- 全セッション共通ルール: **1セッションで publish 系の外部アクションは行わない**（承認キュー方式のため、暴走しても最悪「ドラフトが増える」だけで実害が出ない設計）
