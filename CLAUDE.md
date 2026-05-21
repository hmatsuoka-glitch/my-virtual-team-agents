# my-virtual-team-agents — Claude Code 規約

このリポジトリは Claude Code の subagent 定義集です。`.claude/agents/**/*.md` 配下のファイルは **同期スクリプトが管理する自動生成物** であり、本リポジトリで直接編集しないでください。

## 編集ルール

- **`.claude/agents/` 配下のファイルは直接編集禁止**
  - 編集する場合は上流の `~/my-virtual-team/agents/` を編集する
  - 翌朝の launchd auto-commit がここに反映する
- **frontmatter（`name` / `description`）は手動で書き換え可**
  - 一度書き換えれば、以降の同期では本文だけが更新され、frontmatter は維持される
- **README / AGENTS.md / CLAUDE.md（このファイル）は直接編集 OK**

## ブランチ運用

- `main` のみ。daily の auto-commit が直接 push する
- 大きな構成変更は別ブランチでPR

## エージェントの起動方法

Claude Code は `.claude/agents/**/*.md` を再帰的に探索し、frontmatter の `name` で subagent を識別します。Task tool の `subagent_type` パラメータ、または `@<name>` 形式で呼び出します。
