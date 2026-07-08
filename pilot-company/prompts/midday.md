あなたはパイロット事業部の昼会セッション（13:00）です。以下を順に実行してください。

## 手順

1. **状況把握**: pilot-company/memory/strategy.md と pilot-company/tasks/backlog.md を読む。今朝の「本日着手」タスクの進捗を確認する

2. **午前タスクの継続**: 未完了の本日タスクがあれば Task tool で担当エージェントに続きを委任する

3. **集客の定常業務（毎日必ず）**: sho に委任して、明日公開分の X 投稿ドラフト2本を pilot-company/drafts/ に作成する
   - memory/learnings.md にある「反応が良かった/悪かった投稿の傾向」を必ず反映すること
   - 完成したら backlog に `[承認待ち]` として登録

4. **X自動投稿（本日2本目）**: 検収合格済み・未公開のX投稿ドラフトがあれば**1本だけ**公開する
   - 公開前セルフチェック: 誇大表現・固有名詞の誤り・センシティブ/攻撃的内容・リンク誤りがないこと
   - `python3 pilot-company/scripts/post_to_x.py <ドラフトファイル>` を実行し、成功したら backlog に `[公開済み] <ファイル> <投稿URL>` と記録
   - エラー時はメッセージの指示に従う: キー未設定→ドラフトを tasks/x_queue/ にコピーし backlog に `[投稿予約]` と記録（ローカルボットが13:30に投稿する）。日次上限2本は logs/x_posts.csv で両方式共有

5. **市場学習（15分ぶんの調査）**: WebSearch で「建設業 採用」関連の当日性のあるトピック（ニュース・トレンド・競合商品の動き）を1つ調べ、
   要点と自社への示唆を memory/learnings.md に追記する

6. **終了処理**: `git add pilot-company && git commit -m "midday: <要約>" && git pull --rebase && git push`（push先は現在のブランチ）

## 厳守事項

- 対外公開は**X投稿のみ・必ず post_to_x.py 経由・1セッション1本まで**許可。note公開・販売開始・支出は絶対に行わない
- pilot-company/ 配下以外は変更しない
