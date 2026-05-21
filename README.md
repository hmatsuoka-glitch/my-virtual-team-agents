# my-virtual-team-agents

株式会社LET（SNSマーケ×採用支援「サクバズ」）のバーチャルチームを **Claude Code の subagent 形式** で利用するためのリポジトリです。

このリポジトリは [hmatsuoka-glitch/my-virtual-team](https://github.com/hmatsuoka-glitch/my-virtual-team)（スキル版）から自動同期されます。ローカルの `~/my-virtual-team` で毎日0:00に走る Daily Agent Enhancement の更新内容が、launchd の auto-commit ジョブによって本リポジトリにもミラーされます。

## このリポジトリの位置付け

| リポジトリ | 用途 | 起動形態 |
| --- | --- | --- |
| my-virtual-team（スキル版） | Claude のスキルとして `SKILL.md` ベースで起動 | Skill 起動 |
| **my-virtual-team-agents（本リポジトリ）** | Claude Code / Agent SDK の **subagent** として起動 | Task tool / Agent 呼び出し |

両者は中身が同期されているため、好みの起動方法を選択できます。

## ディレクトリ構造

```
my-virtual-team-agents/
├── README.md                  # このファイル
├── AGENTS.md                  # 全エージェント一覧と簡易説明
├── CLAUDE.md                  # Claude Code 用のリポジトリ規約
├── .claude/
│   └── agents/                # ★ subagent 定義（Claude Code が自動認識）
│       ├── 00-COO/sora.md
│       ├── 01-経営企画部/haruto.md
│       ├── 02-SNS運用部/sho.md
│       └── ... (36 agents)
└── .gitignore
```

各エージェント Markdown には冒頭に YAML frontmatter（`name`, `description`）が付与されており、Claude Code の Task tool から名前で呼び出せます。

## 使い方（Claude Code から呼び出す）

このリポジトリのルートで Claude Code を起動すると、`.claude/agents/**/*.md` が自動的に subagent として認識されます。

```text
# 例: Sho（SNS運用部）に投稿企画を依頼
> @sho-sns 翔星建設の5月の月次投稿カレンダーを作って

# 例: Kaito（LP複製部）にLP複製を依頼
> @kaito 以下のURLを複製してください: https://example.com
```

## 同期の仕組み

ローカル Mac の `~/my-virtual-team/scripts/auto-commit.sh` が launchd 経由で毎朝走り、

1. `my-virtual-team`（スキル版）への commit & push
2. `my-virtual-team-agents`（本リポジトリ）への frontmatter 維持つき同期 & commit & push

を順に実行します。手動で同期したい場合は：

```bash
bash ~/my-virtual-team/scripts/sync-to-agents.sh
```

## ライセンス

[LICENSE](./LICENSE) を参照。
