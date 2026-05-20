# Lane 2: approval_rate 計測 + L1-L6 14 日 PASS 率集計

## メタ情報

| 項目 | 値 |
|---|---|
| Lane | 2 / Phase「ローンチ判定 KPI 定量化」 |
| Tier | **B** (`scripts/` 新規 + `docs/launch/` 配下、既存 SQL/API は read only) |
| auto-merge | **OK** (DoD 全通過時) |
| night-mode 投入 | **22:00 以降 〜 翌 04:00** (想定所要 4-6 h) |
| owner | Claude Code CLI bg lane (sonnet 4.6) |
| 関連 roadmap | `docs/launch/roadmap_to_launch.md` §4.2 / §4.3 (実機データ再計算) |
| 関連既存 script | `scripts/healthcheck_l1_l6.sh`, `scripts/slack_approval_bot.py` |

## /goal

**ローンチ判定 5 条件のうち 2 つの KPI を実機データで定量化する**:
1. **approval_rate**: production の `proposals` テーブル + Slack approval bot の操作ログから「直近 14 日の人間承認率」を計測
2. **L1-L6 14 日 PASS 率**: `scripts/healthcheck_l1_l6.sh` の log を 14 日集計し、各層の PASS / FAIL 比率を出す

両 KPI を `docs/launch/metrics/2026-MM-DD_kpi_snapshot.md` に記録し、roadmap §4 の TBD を埋める材料にする。

## 触るファイル (Tier 抵触チェック)

| ファイル | 種別 | Tier | 抵触 |
|---|---|---|---|
| `scripts/measure_approval_rate.sh` | 新規 | B | なし |
| `scripts/measure_l1_l6_pass_rate.sh` | 新規 | B | なし |
| `scripts/measure_kpi_snapshot.sh` | 新規 (orchestrator) | B | なし |
| `backend/app/automation/kpi_aggregator.py` | 新規 (集計 module、router 配線なし) | B | なし — 既存 `automation/__init__.py` 等 read only |
| `backend/tests/automation/test_kpi_aggregator.py` | 新規 | B | なし |
| `docs/launch/metrics/` | 新規 | B | なし |
| `backend/app/automation/scheduled_tasks.py` | **read only** | S | **触らない** |
| `backend/app/main.py` | **read only** | S | **触らない** (router 配線も今回はしない、CLI script 経由で実行) |
| production DB | **SELECT only** | — | **INSERT/UPDATE/DELETE 禁止** (CLAUDE.md §テストデータ投入制限) |

## 前提確認 (Lane 開始直後、5 分以内)

```bash
cd /opt/ultra-autotrade/main

# 1. healthcheck_l1_l6.sh のログ出力先確認
grep -E "LOG_FILE|tee|>>" scripts/healthcheck_l1_l6.sh | head -10

# 2. production DB から proposals テーブルのスキーマ確認 (CLAUDE.md §2026-05-15 docs/ops/02 推測禁止)
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c '\\d proposals'"

# 3. slack_approval_bot.py の出力 / DB 書き込み確認
grep -E "INSERT|UPDATE|table" scripts/slack_approval_bot.py | head -20

# 4. 直近 14 日の proposals 件数 (recipe の baseline)
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
   \"SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM proposals WHERE created_at > NOW() - INTERVAL '14 days'\""
```

**docs/ops/02_db_tables.md を必ず先に読む** (CLAUDE.md §2026-04-15 教訓: 本番 DB 推測禁止 / カラム名を推測しない)。

## 実装手順

### Step 1: approval_rate 計測の定義確定 (30 min)

`docs/launch/metrics/approval_rate_definition.md` に以下を明確化:

| 用語 | 定義 |
|---|---|
| 提案 (proposal) | `proposals` テーブル 1 row。AI が BUY/SELL 判定で生成 |
| 承認 (approval) | `proposals.status = 'approved'` または `proposals.executed_at IS NOT NULL` (実装に応じて判定) |
| 拒否 (reject) | `proposals.status = 'rejected'` |
| 期限切れ (expired) | `proposals.expires_at < NOW()` かつ未処理 |
| 計測対象期間 | 直近 14 日 (`created_at > NOW() - INTERVAL '14 days'`) |
| approval_rate | `承認 / (承認 + 拒否 + 期限切れ)` (分母から「未処理かつ未期限切れ」は除外) |

**山本さん UAT 中は承認操作が「テスト目的の操作」になるため、approval_rate を「品質指標」として扱うには context 付き解釈が必要** — roadmap §1 条件 4 (UAT 14 日観測) と組合せて評価。

### Step 2: measure_approval_rate.sh 実装 (60 min)

```bash
#!/bin/bash
# scripts/measure_approval_rate.sh
# production DB から直近 N 日の approval_rate を計算。SELECT only.

set -euo pipefail

DAYS="${1:-14}"
OUTPUT_DIR="${OUTPUT_DIR:-docs/launch/metrics}"
TODAY=$(date +%Y-%m-%d)
mkdir -p "$OUTPUT_DIR"

# CLAUDE.md §2026-05-13 教訓 策7: heredoc で SQL 渡す
RESULT=$(ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 <<ENDSSH
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -t -A -F'|' <<SQL
SELECT
  COUNT(*) FILTER (WHERE status = 'approved') AS approved,
  COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
  COUNT(*) FILTER (WHERE status = 'pending' AND expires_at < NOW()) AS expired,
  COUNT(*) FILTER (WHERE status = 'pending' AND expires_at >= NOW()) AS pending,
  COUNT(*) AS total
FROM proposals
WHERE created_at > NOW() - INTERVAL '${DAYS} days';
SQL
ENDSSH
)

# RESULT を parse して approval_rate を計算 + JSON 出力
# 出力先: docs/launch/metrics/${TODAY}_approval_rate.json
```

**注意点**:
- `proposals.status` の実カラム名・値は **Step 0 で docs/ops/02 で確認** (CLAUDE.md 「テーブル名から機能を推測しない」)
- production DB は read only (SELECT のみ、INSERT/UPDATE/DELETE 禁止)
- CF Access が必要な場合は service token を env 経由

### Step 3: measure_l1_l6_pass_rate.sh 実装 (60 min)

```bash
#!/bin/bash
# scripts/measure_l1_l6_pass_rate.sh
# healthcheck_l1_l6.sh の log を 14 日集計

set -euo pipefail

DAYS="${1:-14}"
LOG_PATH="/opt/ultra-autotrade/logs/healthcheck_l1_l6.log"  # Step 1 確認結果で確定
OUTPUT_DIR="${OUTPUT_DIR:-docs/launch/metrics}"
TODAY=$(date +%Y-%m-%d)
mkdir -p "$OUTPUT_DIR"

# 本番 VPS の healthcheck log を pull
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
  "tail -n 10000 ${LOG_PATH}" > /tmp/healthcheck_l1_l6_pulled.log

# log を 14 日 × L1-L6 × PASS/FAIL でクロス集計
# 出力: docs/launch/metrics/${TODAY}_l1_l6_pass_rate.json
```

**healthcheck_l1_l6.sh のログ format を Step 1 で確認**してから parse 実装。format が不明なら本 Lane で format 仕様も `docs/launch/metrics/l1_l6_log_format.md` に書き出す。

### Step 4: kpi_aggregator.py (60 min)

pytest 可能な Python module として、`backend/app/automation/kpi_aggregator.py` に approval_rate + L1-L6 PASS 率の計算ロジックを実装。CLI script はこれを呼び出す薄い wrapper にする。理由: shell の集計はテストしにくい、Python なら pytest で 80% coverage 達成しやすい。

**重要**: router (`main.py` 配線) は **本 Lane では追加しない**。Tier S 抵触防止のため CLI script 経由のみ。後続 Lane で router 必要になったら別 PR で main.py 追記する。

### Step 5: kpi_snapshot 出力 + roadmap §4 への反映依頼 (30 min)

```bash
# scripts/measure_kpi_snapshot.sh
# 全 KPI を 1 度に取得して docs/launch/metrics/YYYY-MM-DD_kpi_snapshot.md にまとめる

./scripts/measure_approval_rate.sh 14
./scripts/measure_l1_l6_pass_rate.sh 14
# 追加 KPI (CLAUDE.md §2026-05-13 教訓 策1 推奨):
#   - ai_decisions 24h 件数
#   - proposals 24h 件数 + MAX(created_at)
#   - final_action 別 7 日件数
```

出力テンプレ:

```markdown
# KPI Snapshot 2026-MM-DD

## Summary
- 計測時刻: ISO8601
- 計測期間: 直近 14 日

## approval_rate
- approved: N
- rejected: N
- expired: N
- pending: N (分母外)
- approval_rate: X.X% (approved / (approved+rejected+expired))

## L1-L6 PASS 率 (14 日)
| Layer | PASS | FAIL | rate |
|---|---|---|---|
| L1 | N | N | X.X% |
| ... | | | |

## AI 判定 KPI
- 24h ai_decisions: N
- 24h proposals: N (MAX(created_at): TS)
- 7d final_action breakdown: BUY:N / SELL:N / HOLD:N

## 既知の制約
- 山本さん UAT 中は approval_rate に test 操作が混入
- TBD: 山本さん操作のみ除外するフィルタを後続 Lane で追加するか議論
```

## DoD

### A. 機能完了
- [ ] 3 scripts (`measure_approval_rate.sh` / `measure_l1_l6_pass_rate.sh` / `measure_kpi_snapshot.sh`) staging + dev VPS で動作確認
- [ ] `backend/app/automation/kpi_aggregator.py` 実装 + pytest 80% coverage
- [ ] **本日分の kpi_snapshot** が `docs/launch/metrics/YYYY-MM-DD_kpi_snapshot.md` に出力済み
- [ ] roadmap_to_launch.md §4.2 / §4.3 に snapshot 値貼付 (TBD 解消)

### B. Gate 全通過
- [ ] Gate 1-3: `./scripts/verify.sh` 全 pass
- [ ] Gate 4: Playwright E2E — **N/A** (UI 変更なし)
- [ ] Gate 5: 孤立コード検出 — **必須** (`kpi_aggregator.py` の関数が CLI 経由で呼ばれていることを grep で証明)
- [ ] Gate 6: Codex Review (`/codex:review --base main --background`) — **必須**
- [ ] Gate 7: Claude in Chrome — **N/A**
- [ ] Gate 8: deploy 後外形 `/health` — **N/A** (本 Lane は deploy しない)

### C. 教訓記録
- [ ] DB スキーマ推測ミス / log format 推測ミス等を CLAUDE.md「教訓-2026-05-2X」に追記 (なければ「特記なし」)

### D. Asana 連携
- [ ] PR description に Asana GID + Closes
- [ ] Lane 完了時 notes に PR link + Gate 結果 + 教訓サマリ

### E. Slack JSON 通知
```json
{
  "lane": "2",
  "phase": "ローンチ判定 KPI 定量化",
  "status": "completed",
  "tier": "B",
  "gate_results": {
    "1-3_verify": "pass",
    "4_e2e": "n/a",
    "5_dead_code": "pass",
    "6_codex": "approved",
    "7_chrome": "n/a",
    "8_health": "n/a"
  },
  "kpi_values": {
    "approval_rate_14d": "X.X%",
    "l1_l6_pass_rate_14d": {"L1": "...", "...": "..."},
    "ai_decisions_24h": N,
    "proposals_24h": N
  },
  "pr_url": "...",
  "next_action": "roadmap §4.2/§4.3 TBD 解消"
}
```

### F. claude.ai 引継ぎ
- [ ] PR URL / KPI 値 / 「山本さん UAT 操作除外」議論ポイント
- [ ] roadmap §1 条件 (5 条件のうち approval_rate / L1-L6 14日 PASS が直接関連する条件) に値を貼付する作業依頼

## 制約 (絶対遵守)

1. **production DB は SELECT only** (INSERT/UPDATE/DELETE 禁止、CLAUDE.md §テストデータ投入制限)
2. **production への ALTER TABLE / 新規 column 追加禁止** (本 Lane は計測のみ、スキーマ変更は後続 Lane)
3. **scheduled_tasks.py / main.py / docker-compose は touch 禁止** (Tier S)
4. **CF Access service token を log に出さない** (CLAUDE.md §Security Rules: No tokens/keys in logs)
5. **docs/ops/02_db_tables.md を必ず先に読む** (CLAUDE.md §2026-04-15 教訓)
6. **テーブル名・カラム名を推測しない** (CLAUDE.md §2026-05-13 教訓 策 8)
7. **SQL は heredoc で渡す** (CLAUDE.md §2026-05-13 教訓 策 7、INTERVAL の quote 問題回避)

## References

- `docs/launch/roadmap_to_launch.md` §4.2 / §4.3
- `docs/ops/02_db_tables.md` (`proposals` テーブルのスキーマ)
- `scripts/healthcheck_l1_l6.sh` (既存 L1-L6 check)
- `scripts/slack_approval_bot.py` (approval 操作の data source)
- `CLAUDE.md` §テストデータ投入制限 (2026-05-02)
- `CLAUDE.md` §2026-05-13 教訓 策 1 (業務 KPI 朝確認 SQL)
- `CLAUDE.md` §2026-04-15 教訓 (本番 DB 操作ルール)

## 推定所要時間内訳

| 工程 | 想定 |
|---|---|
| 前提確認 + docs/ops/02 通読 | 30 min |
| Step 1 定義確定 | 30 min |
| Step 2 approval_rate script | 60 min |
| Step 3 L1-L6 PASS 率 script | 60 min |
| Step 4 kpi_aggregator.py + pytest | 90 min |
| Step 5 snapshot 出力 + roadmap 連携 | 30 min |
| Gate 1-6 通過 + PR + Slack | 60 min |
| **合計** | **5-6 h** |
