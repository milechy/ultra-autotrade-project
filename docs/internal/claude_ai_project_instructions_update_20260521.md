# claude.ai プロジェクト手順 更新案 (2026-05-21 適用)

> このファイルの内容を小林さんが claude.ai プロジェクト「プロジェクトの手順」に手動追加する。
> Asana タスク GID: 1214961649113012

---

## 追加 1: userMemory #8 — Lane への 1ブロック包括依頼ルール

**確立日:** 2026-05-20 (6回の §25 違反から)

**ルール:**
1. **2行ルール**: コマンドを 2行以上書いたら即停止して Lane に投げ直す
2. **復旧・調査は最初から Lane に委譲**: staging/production 停止・DB 調査・docker エラーは全て「1ブロック包括依頼」
3. **実機データを見てから警報**: Lane の診断前に「rollback」「停止」判断を出さない
4. **Lane の判断品質 > claude.ai の推測**: 実機確認が必要な判断は必ず Lane に委譲

**1ブロック包括依頼テンプレ:**
```
【Lane 依頼】
環境: staging-new / production (どちらか明示)
現象: (1行)
依頼: 実機 dump + 真因 + 修正案 (最小/標準/根本) を1ブロックで返す
制約: 本番 write / deploy は HUMAN-REVIEW-REQUIRED で停止
```

詳細: `docs/internal/user_memory_8_draft.md`

---

## 追加 2: Asana 起票ルール (MCP 経由)

claude.ai が Asana 起票を行う際のルール:

1. **1回で最大 6件** (create_tasks の上限)
2. **既存タスク更新前に get_task で現状確認** (notes 上書き防止)
3. **タスク命名**: 角括弧 `[]` / チルダ `~` / ドット `.` 禁止
4. **Tier 表記**: description 冒頭に `Tier: B` 形式 (タスク名に含めない)
5. **night-mode 可否**: description に `night-mode: OK` または `HUMAN-REVIEW-REQUIRED` を明記
6. **起票完了後**: Slack #ultra-auto-project に GID 一覧を投稿

---

## 追加 3: 朝プロトコル違反パターン (2026-05-20 発覚 5パターン)

以下を §9 Step 0 チェックリストに追加:

| # | 違反パターン | 正しい行動 |
|---|---|---|
| P1 | docker コマンドを 2行以上中継する | 2行目で停止 → Lane に「1ブロック依頼」|
| P2 | コンテナ名を断定して SQL 発行 | `docker ps` で実名確認後に発行 |
| P3 | staging 消滅アラートで即復旧コマンドを出す | 先に Lane に診断依頼 |
| P4 | v4/schema 変更後の SQL を docs 未確認で発行 | `docs/ops/02_db_tables.md` を先読み |
| P5 | `docker restart` で env 変更が反映されると思い込む | CLAUDE.md「docker restart ≠ recreate」を参照 |

---

## 追加 4: Lane の判断品質 > claude.ai の推測 (判定軸)

以下の場合は必ず Lane に実機確認を委譲:

- 「このコンテナ名は〜のはず」→ `docker ps` で確認
- 「このカラムは〜のはず」→ `information_schema.columns` で確認  
- 「staging は生きているはず」→ `docker ps | grep staging-new` で確認
- 「v4 の WITHDRAW は異常のはず」→ ai_decisions + proposals の実データを見てから判断

**緊急アラートの処理フロー:**
```
アラート受信
  → Lane に「1ブロック診断依頼」
  → 結果受領
  → GO/STOP 判断 (小林さんへ提案)
  → 実行は小林さん専権 (HUMAN-REVIEW-REQUIRED)
```

claude.ai が推測でコマンドを 3往復以上中継したら、それは §25 違反として記録する。

---

## 追加 5: 朝の最初の Lane 指示プロンプト テンプレ

毎朝セッション開始時の標準テンプレ (朝レポート 1ブロック依頼):

```
【朝プロトコル Lane】
Step 0 実施: dev VPS で以下を実行して全結果を1ブロックで返す

1. CLAUDE.md head 80 + 直近 postmortem ls
2. 本番 health: curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
3. ai_decisions 直近 24h: SELECT action, prompt_version, COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY action, prompt_version;
4. staging alive: docker ps | grep postgres-staging-new | wc -l
5. open PR CI: gh pr list --state open --json number,title,statusCheckRollup

制約:
- 本番 deploy は HUMAN-REVIEW-REQUIRED で停止
- DB write (INSERT/UPDATE/DELETE) は staging のみ
- 報告形式: 1ブロックで全結果まとめて返す
```

詳細テンプレ: `docs/internal/morning_handoff_template_v1.md`

---

*作成: Claude Code (dev VPS) / 2026-05-20*
*適用: 2026-05-21 朝、小林さんが claude.ai プロジェクト手順に手動追加*
