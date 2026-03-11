# 27_asana_operations.md
# Asana 運用ルール

> **最終更新:** 2026-03-11 (Stream K)

---

## 1. プロジェクト構成

Ultra AutoTrade の Asana プロジェクトは以下のセクションで管理する。

| セクション | 用途 |
|-----------|------|
| `📋 Backlog` | 未着手タスク（優先度未定） |
| `🔄 In Progress` | 現在進行中のタスク |
| `✅ Done` | 完了タスク |
| `⚠️ Overdue` | 期限超過タスク（自動 / 手動で移動） |

---

## 2. タスク命名規則

```
<ファイルパス or 機能名> → <作業内容>
例:
  docs/04 → API設計書更新 (/knowledge/*, /exchange/*)
  backend/ai → Two-Phase 判定実装
  Stream K: ドキュメント整備
```

---

## 3. 優先度

| 優先度 | 基準 |
|--------|------|
| High | セキュリティ・本番リリースブロッカー |
| Medium | 機能実装・ドキュメント整備 |
| Low | Nice-to-have・将来対応 |

---

## 4. Due Date ルール

- **新規タスク:** 作成時に必ず Due Date を設定すること
- **Stream タスク:** 各 Wave の終了日を Due Date とする
- **期限超過タスク:** 毎週月曜に一括レビュー → 期限延長または Close

---

## 5. Stream（波）管理

各開発サイクルを Stream と呼び、Asana でタグ管理する。

| Stream ID | タグ | 担当領域 |
|-----------|------|---------|
| stream-a | `stream-a` | Knowledge Hub |
| stream-b | `stream-b` | Exchange |
| stream-c | `stream-c` | AI 判定 |
| stream-d | `stream-d` | Aave |
| stream-e | `stream-e` | フロントエンド |
| stream-f〜j | 各タグ | 順次割り当て |
| stream-k | `stream-k` | ドキュメント整備 |

---

## 6. タスク完了基準

タスクを「完了」にするのは以下を全て満たした場合のみ。

- [ ] 実装（またはドキュメント更新）完了
- [ ] DoD チェック通過（`/verify` コマンド）
- [ ] PR 作成 → レビュー承認 → `dev` マージ済み
- [ ] Staging 動作確認完了（バックエンド変更の場合）

---

## 7. 週次レビュー手順

毎週月曜に実施。

1. Asana で Due Date が過去のタスクを検索
2. 各タスクについて:
   - 完了済みなら `completed = true` にする
   - 未着手 / 継続中なら Due Date を延長（理由を Asana コメントに記載）
   - 不要になったタスクは Archived に移動
3. 週次サマリーを Slack `#ultra-autotrade-dev` に投稿

---

## 8. NG 操作

- 完了していないタスクを `completed = true` にしない
- Due Date なしのタスクを Backlog に放置しない（最長 2 週間以内に設定）
- 1 タスクに複数の担当者を割り当てない（Owner は 1 人）
