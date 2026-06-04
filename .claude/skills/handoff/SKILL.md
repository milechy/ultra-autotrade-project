---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work.

## 保存先

`/home/uata/handoffs/YYYY-MM-DD_<topic>.md` に保存する（OS の tmp ディレクトリではない）。
- `YYYY-MM-DD` は今日の日付（例: 2026-06-02）
- `<topic>` はセッションの主題を snake_case で 3-5 単語（例: `aave_custodial_fix`）
- ファイル保存後、絶対パスをユーザーに伝えること

## 必須セクション

ドキュメントには以下を必ず含める:

### 1. Goal
何を達成しようとしているか（1-3 行）

### 2. Current Progress
- 完了済みタスク（commit hash / PR URL 付き）
- 未完了タスク

### 3. Lane 状態
並列レーンを実行中の場合:
- 各 Lane の状態（running / blocked / completed）
- Lane ごとの worktree ブランチ名
- 次のアクション

### 4. PR + Gate 状態
- 関連 PR 番号と URL
- Gate 1-7 の通過状況（pass / fail / n/a）
- CI の状態

### 5. Staging Health
staging 環境の現状（確認済みの場合）:
- `curl http://127.0.0.1:8082/health` 結果
- 直近の deploy commit
- Shadow Mode / AI スケジューラの状態

### 6. Asana タスク番号
- 関連 Asana タスクの GID と名前
- 現在の状態（未着手 / 進行中 / 完了）

### 7. What Worked / What Didn't Work
- 成功したアプローチ（繰り返し推奨）
- 失敗したアプローチ（重複防止のため必ず記録）

### 8. Next Steps
次のエージェントへの明確なアクションリスト（優先順）

### 9. Suggested Skills
次のエージェントが呼び出すべきスキルの提案

## 一般ルール

- PRD / ADR / issue / diff 等の既存アーティファクトは内容を重複させず、パスまたは URL で参照する
- API キー / パスワード / 個人情報は必ずリダクトする
- 引数が渡された場合は、それを次セッションのフォーカスとして文書に反映する
