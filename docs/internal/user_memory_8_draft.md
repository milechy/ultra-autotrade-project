# userMemory #8 — 2026-05-20 終日教訓 (claude.ai プロジェクト手順追加用)

> このファイルを明朝小林さんが claude.ai プロジェクト「プロジェクトの手順」に手動追加する。
> Asana タスク GID: 1214961786655549

---

## userMemory #8: Lane への 1ブロック包括依頼ルール

**確立日:** 2026-05-20

### 違反パターン (本日 6回発生)

| # | 違反内容 | 正しい行動 |
|---|---|---|
| 1 | docker restart で env 変更が反映されると思い込んだ | `--force-recreate` 要否を CLAUDE.md で確認してから指示 |
| 2 | staging 消滅アラートを受けて即 `docker compose up -d` を中継した | 先に Lane に「staging 死活 + 真因 + 復旧案 1ブロック」を依頼 |
| 3 | proposals スキーマを推測して `confidence` カラムを含む SQL を発行した | `docs/ops/02_db_tables.md` を先読みしてからクエリ生成 |
| 4 | fund_allocations の `user_id` カラムを推測した | 同上 |
| 5 | AI_PROMPT_VERSION=v4 確認 SQL を schema 未確認で発行した | `docs/ops/02_db_tables.md` 確認後に発行 |
| 6 | 復旧コマンドを 3行以上中継し続けた | 2行目で停止して Lane に投げ直す |

### 新規ルール

**ルール 1: 2行ルール**
コマンドを 2行以上書いたら即停止して Lane に「1ブロック包括依頼」を投げ直す。
claude.ai がコマンドを連鎖させることは §25 違反。

**ルール 2: 復旧・調査は最初から Lane に委譲**
- staging/production 停止 → Lane に「現状 dump + 真因 + 復旧プラン」を1ブロック依頼
- DB 調査 → Lane に「対象テーブルのスキーマ確認 + クエリ実行 + 結果解釈」を1ブロック依頼
- docker 系エラー → Lane に「コンテナ状態 + ログ + 修正手順」を1ブロック依頼

**ルール 3: 実機データを見てから警報**
緊急アラートを受けても、Lane の診断結果が来るまで「rollback」「停止」の判断を出さない。
本日の WITHDRAW 調査: 実機データで「安全確認 → GO」が正解だった。

**ルール 4: Lane の判断品質 > claude.ai の推測**
Lane は実コードを grep し、実 DB をクエリし、実ログを確認する。
claude.ai は記憶と推測で動く。実機確認が必要な判断は必ず Lane に委譲する。

### 1ブロック包括依頼テンプレ

```
【Lane 依頼】
環境: staging-new / production (どちらか明示)
現象: (1行で)
依頼: 以下を1ブロックで返す
  1. 実機 dump (docker ps / logs / DB query 等)
  2. 真因 (推測ではなく実データから)
  3. 修正案 (最小/標準/根本 の3択)
制約: 本番 DB write / deploy は HUMAN-REVIEW-REQUIRED で停止
```

---

*作成: Claude Code (dev VPS) / 2026-05-20*
*追加先: claude.ai プロジェクト「プロジェクトの手順」> userMemories セクション*
