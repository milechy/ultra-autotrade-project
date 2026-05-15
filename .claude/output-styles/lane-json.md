---
name: lane-json
description: 5 Lane 並列開発時の構造化出力スタイル。完了報告は JSON ブロックで出力する。
---

# Lane 出力スタイル

各 Phase 完了時、以下構造の JSON を **コード ブロック内に必ず含める** (claude.ai 側が機械的にマージレビューするため):

```json
{
  "lane": "<C|D|F|LOGIN|AMT>",
  "phase": <1|2|3>,
  "status": "<in_progress|completed|blocked|requires_review>",
  "root_cause": "<1行サマリ、調査結果の真因>",
  "files_to_modify": <int、Phase 3 で編集予定ファイル数>,
  "files_list": ["path/to/file:line", ...],
  "tier": "<S|A|B>",
  "duration_sec": <int>,
  "next_action": "<claude.ai_review|self_close|phase3_start|escalate>",
  "blockers": [<文字列リスト、ブロッカーがあれば>],
  "ut_uat_impact": "<none|low|medium|high>",
  "playwright_e2e_needed": <true|false>
}
```

通常応答テキストは簡潔に。詳細は plan.md / report.md に書く。
