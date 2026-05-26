# production alembic 同期 runbook — #398 前提手順 (2026-05-26)

> 本 runbook は **read-only 調査 + dev VPS 内検証のみ**で起草。**production への実行は 0 件**。
> 実行は本 PR merge 後、別セッションで HUMAN-REVIEW STOP を踏みながら行う。
>
> 関連 PR: #398 (`fix(alembic): g7 down_revision を a7 に張り替え、多頭分岐解消 [Tier S]`)
> 関連 runbook: `docs/internal/2026-05-23_backend_codeploy_runbook.md` (#369/#373/#374 + R-6)

---

## 0. 目的 / 背景

### 解消すべき問題

`docs/internal/2026-05-23_backend_codeploy_runbook.md ②-a` は production で
`alembic current` が `f6a7b8c9d0e1` を返すことを前提にしている。だが本プロジェクトは
**2026-04-05 教訓 (`CLAUDE.lessons.md:205-207`)** で「DB マイグレーションは手動
`ALTER TABLE` 方式」と明文化しており、`docker-compose.production.yml` の command にも
`alembic` を含めていない。したがって **production の `alembic_version` テーブルは存在しない可能性が高い**。

その状態で `alembic upgrade head` を流すと alembic は base (`59919a6d4848`) から
全マイグレーションを再適用しようとし、既存テーブルに `CREATE TABLE` が衝突して deploy が止まる。

### #398 との関係

#398 は dev 側の多頭分岐 (a7 と g7 が同じ down=f6) を解消し、`alembic heads` を
`g7h8i9j0k1l2` 単独に戻す PR。#398 の merge は本 stamp 同期の **必要条件**だが
**十分条件ではない**: stamp が無いまま #398 を merge しても production で
`alembic upgrade head` は実行できない。

本 runbook の目的:

1. production に **`alembic_version` テーブルを 1 行ぶんだけ作成**し、現スキーマと一致する
   revision を stamp する。
2. 以後の deploy で `alembic upgrade head` が「未適用 migration の差分だけ」を流す状態にする。
3. #398 merge 後、`alembic current` → `f6a7b8c9d0e1` → `alembic upgrade head` で
   a7 → g7 が 1 度だけ流れる線路を敷く。

### 実行禁止事項 (ABSOLUTE)

- 本 runbook の curl / docker exec / SQL を **dev VPS 起草段階で production に対して実行してはならない**。
- `alembic stamp head` (revision 省略) を打たない。stamp 先は必ず明示。
- backup を取らずに `alembic stamp` を流さない。
- 別作業 (#369/#373/#374 deploy など) と同セッションで束ねない。stamp 同期は単独 PR / 単独 deploy で実施する。

---

## 1. 前提条件 (実行前ゲート)

本 runbook を実行する前に、以下すべてが満たされていること。

| # | 条件 | 確認方法 |
|---|------|----------|
| 1 | PR #398 が main にマージ済み | `gh pr view 398 --json state,mergedAt` |
| 2 | dev VPS で `alembic heads` が `g7h8i9j0k1l2` 単独 | dev VPS の `backend/.venv` 内で `alembic heads` |
| 3 | 直近 24h で production の自動バックアップ成功 | `scripts/backup_db.sh` のログ / S3 オフサイト先 |
| 4 | production AI scheduler 停止状態 (任意推奨) | `.env.production` の `DISABLE_AI_JUDGMENT_SCHEDULER` / 既知 scheduler ロック |
| 5 | `2026-05-23_backend_codeploy_runbook.md ②-a` を**未実行** | runbook 完了通知の有無 (実行済みなら本 runbook は不要、別問題) |

★条件 5 が未確定なら STOP。HUMAN-REVIEW で 5/23 runbook の実施有無を確認してから着手。

---

## 2. Phase A — 実機調査 (read-only / 推定所要 5 分)

### A-1. `alembic_version` テーブルの有無を確認

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155
cd /opt/ultra-autotrade
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "SELECT to_regclass('public.alembic_version');"
```

★STOP — 結果による分岐:

- 結果 `(null)` → **テーブル不在 (想定どおり)**。Phase B (schema fingerprint) へ進む。
- 結果 `alembic_version` → **テーブル存在**。本 runbook は適用不可。
  代わりに以下を流し、stamp 値を確認してから claude.ai に報告:
  ```bash
  docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
    -c "SELECT version_num FROM alembic_version;"
  ```
  既知 revision (本 PR 時点で `59919a6d4848` 〜 `g7h8i9j0k1l2` の 9 件) と
  一致するなら `2026-05-23_backend_codeploy_runbook.md ②-a` に直接接続できる。
  未知 revision (typo / 古い branch の残骸) なら HUMAN-REVIEW STOP。

### A-2. schema fingerprint 採取

stamp すべき revision を決めるため、各 migration が残す **DB 上の痕跡**を読み取る。
すべて SELECT のみで write しない。

```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade <<'SQL'
\echo '=== fingerprint 1: 59919a6d4848 base (core tables) ==='
SELECT count(*) AS core_tables_present FROM information_schema.tables
WHERE table_schema='public'
  AND table_name IN ('ai_decisions','users','proposals','transactions',
                     'portfolio_snapshots','portfolio_history','user_settings',
                     'knowledge_documents','knowledge_chunks','knowledge_sources');

\echo '=== fingerprint 2: a1b2c3d4e5f6 (user_mode + execution_policy) ==='
SELECT column_name FROM information_schema.columns
WHERE table_name='users' AND column_name IN ('user_mode','execution_policy')
ORDER BY column_name;

\echo '=== fingerprint 3: b2c3d4e5f6a7 (wallet_address) ==='
SELECT column_name FROM information_schema.columns
WHERE table_name='users' AND column_name='wallet_address';

\echo '=== fingerprint 4: c3d4e5f6a7b8 (error_message on proposals/transactions) ==='
SELECT table_name, column_name FROM information_schema.columns
WHERE table_name IN ('proposals','transactions') AND column_name='error_message'
ORDER BY table_name;

\echo '=== fingerprint 5: d4e5f6a7b8c9 (fee_v10 — v9 撤去 + v10 投入) ==='
SELECT table_name FROM information_schema.tables
WHERE table_schema='public'
  AND table_name IN ('fee_configs','fee_transactions','fee_calculations','high_water_marks')
ORDER BY table_name;
SELECT column_name FROM information_schema.columns
WHERE table_name='fee_configs' AND column_name='tier_thresholds_jpy';  -- v10 専用カラム

\echo '=== fingerprint 6: e5f6a7b8c9d0 (fee_transactions.risk_mode CHECK 内容) ==='
SELECT pg_get_constraintdef(c.oid)
FROM pg_constraint c JOIN pg_class t ON c.conrelid=t.oid
WHERE t.relname='fee_transactions' AND c.conname='chk_fee_tx_risk_mode';

\echo '=== fingerprint 7: f6a7b8c9d0e1 (privy_did) ==='
SELECT column_name FROM information_schema.columns
WHERE table_name='users' AND column_name='privy_did';
SELECT indexname FROM pg_indexes
WHERE tablename='users' AND indexname='ix_users_privy_did';

\echo '=== fingerprint 8: a7b8c9d0e1f2 (users.execution_policy CHECK) ==='
SELECT pg_get_constraintdef(c.oid)
FROM pg_constraint c JOIN pg_class t ON c.conrelid=t.oid
WHERE t.relname='users' AND c.conname='users_execution_policy_check';

\echo '=== fingerprint 9: g7h8i9j0k1l2 (users.execution_policy default) ==='
SELECT column_default FROM information_schema.columns
WHERE table_name='users' AND column_name='execution_policy';

\echo '=== aux: execution_policy 値分布 (g7 適用前 backfill 監査用) ==='
SELECT role, execution_policy, count(*) FROM users
GROUP BY role, execution_policy ORDER BY role, execution_policy;
SQL
```

★出力をすべて claude.ai に貼り戻す。**この時点では stamp 判断を機械で行わない**。

---

## 3. Phase B — stamp 先 revision の決定 (HUMAN-REVIEW / 推定 5-15 分)

### B-1. 判断ロジック

A-2 の fingerprint を上から順に評価し、**「ある」 → 「ない」に切り替わる直前の revision**を stamp 対象とする。

| 判定ステップ | 「ある」とみなす条件 | 真なら次へ / 偽なら stamp 候補 |
|--------------|----------------------|-------------------------------|
| 1. core | `core_tables_present = 10` | 次へ / 偽なら **stamp 不可** (base から CREATE TABLE が必要 → 別 runbook) |
| 2. a1 | `users.user_mode` と `users.execution_policy` 両方存在 | 次へ / 偽なら `59919a6d4848` |
| 3. b2 | `users.wallet_address` 存在 | 次へ / 偽なら `a1b2c3d4e5f6` |
| 4. c3 | `proposals.error_message` と `transactions.error_message` 両方存在 | 次へ / 偽なら `b2c3d4e5f6a7` |
| 5. d4 | `fee_configs.tier_thresholds_jpy` 存在 かつ `fee_calculations` / `high_water_marks` 不在 | 次へ / 偽なら `c3d4e5f6a7b8` |
| 6. e5 | `chk_fee_tx_risk_mode` が `('conservative', 'balanced', 'aggressive')` | 次へ / 偽なら `d4e5f6a7b8c9` |
| 7. f6 | `users.privy_did` カラムと `ix_users_privy_did` index 両方存在 | 次へ / 偽なら `e5f6a7b8c9d0` |
| 8. a7 | `users_execution_policy_check` 制約存在 | 次へ / 偽なら **`f6a7b8c9d0e1`** ★想定 stamp 先 |
| 9. g7 | `users.execution_policy` の column_default が `'require_approval'::*` | (もう head なので stamp 不要) / 偽なら `a7b8c9d0e1f2` |

★ **想定 stamp 先**: `f6a7b8c9d0e1` (引継ぎ通り)。
- 2026-05-23 runbook が `f6a7b8c9d0e1` を前提にしているため、A-2 で 8 が偽 (CHECK 制約なし) であることが想定される。
- もし A-2 で 8 が真 (CHECK 制約あり) なら、stamp 先は `a7b8c9d0e1f2`。理由: a7 を staging で adhoc に適用済みで production にも染み出している可能性は低いが、idempotent 制約なので「あるなら適用済み扱い」で stamp 上げてよい。

### B-2. 中間状態 (混在) パターンへの対応

判定の途中で「ある / ない」が**ジグザグ**する (例: f6 はあるが d4 が無い、a7 はあるが f6 が無い) 場合、
これは手動 ALTER TABLE 運用で migration を**順不同**に適用した痕跡である。

★STOP — このパターンが出たら HUMAN-REVIEW で以下を判断:

1. 不足している中間 migration を **手動 SQL で先に追いつかせる** (整合性復元)
2. その上で最も「進んだ」revision を stamp する
3. 整合性復元の前後で DB バックアップを別途取得する

ジグザグ無し (上から連続して「ある」 → 切り替わり → 連続して「ない」) なら、切り替わり位置の手前を素直に stamp。

---

## 4. Phase C — stamp 実行 (write / 推定 5 分)

> **本 Phase はバックアップ取得後にのみ実行する。**

### C-1. バックアップ取得 (必須)

```bash
cd /opt/ultra-autotrade
./scripts/backup_db.sh  # `docs/ops/03_deploy_procedures.md` 準拠
# または:
docker exec ultra-autotrade-postgres-production \
  pg_dump -U ultra ultra_autotrade > /tmp/backup_pre_alembic_stamp_$(date +%Y%m%d_%H%M%S).sql
ls -lh /tmp/backup_pre_alembic_stamp_*.sql
```

★STOP — backup ファイルサイズが想定範囲 (現状の DB 規模) に収まっていることを確認。

### C-2. stamp dry-run (`--sql` プレビュー)

`alembic` は production の Docker image には未導入 (CLAUDE.lessons.md 2026-04-05 教訓)。
**必ず backend コンテナ内ではなく、`backend` ディレクトリでホストの venv 経由で実行**する。
本番 VPS には dev VPS と同等の `backend/.venv` を事前に用意するか、dev VPS で `--sql` を
生成して結果を SQL ファイルとして production に持ち込む方式を選ぶ。

**推奨**: dev VPS で SQL を生成 → review → production の `psql` で適用。

```bash
# dev VPS 側
cd ~/projects/ultra-autotrade/backend
source .venv/bin/activate
DATABASE_URL=postgresql://dummy:dummy@localhost/dummy \
  alembic stamp f6a7b8c9d0e1 --sql | tee /tmp/stamp_f6.sql
deactivate
```

★STOP — 生成 SQL が以下と一致することを目視で確認:

```sql
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
-- Running stamp_revision  -> f6a7b8c9d0e1
INSERT INTO alembic_version (version_num) VALUES ('f6a7b8c9d0e1');
```

(stamp 先 revision は B-1 で決めた値。`f6a7b8c9d0e1` でない場合は適宜読み替え)

### C-3. production への適用

`/tmp/stamp_f6.sql` を SCP / scp -3 / vi 貼付などで本番 VPS の `/tmp/` に持ち込んだ後:

```bash
ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155
docker cp /tmp/stamp_f6.sql ultra-autotrade-postgres-production:/tmp/stamp_f6.sql
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -v ON_ERROR_STOP=1 -f /tmp/stamp_f6.sql
```

★STOP — exit code 0 を確認。エラーが出たら **ロールバック手順 (§6) を即時実行**。

---

## 5. Phase D — 検証 (read-only / 推定 3 分)

### D-1. stamp 結果確認

```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "SELECT version_num FROM alembic_version;"
# 期待: f6a7b8c9d0e1 (B-1 で決めた値)
```

### D-2. dry-run で次回 upgrade の中身を確認

`alembic` 本体は production VPS に入っていないため、ここでも dev VPS 側で
**production と同じ stamp 値を仮定した dry-run** を行い、出力 SQL を staging などで先に再現する。

```bash
# dev VPS 側 (本番 DB には接続しない)
cd ~/projects/ultra-autotrade/backend
source .venv/bin/activate
DATABASE_URL=postgresql://dummy:dummy@localhost/dummy \
  alembic upgrade head --sql f6a7b8c9d0e1:head | tee /tmp/upgrade_preview.sql
deactivate
```

★STOP — `/tmp/upgrade_preview.sql` の内容が以下 2 段だけであること:

```sql
-- Running upgrade f6a7b8c9d0e1 -> a7b8c9d0e1f2
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_execution_policy_check;
ALTER TABLE users ADD CONSTRAINT users_execution_policy_check
  CHECK (execution_policy IN ('auto_execute', 'require_approval', 'proposal_only'));

-- Running upgrade a7b8c9d0e1f2 -> g7h8i9j0k1l2
ALTER TABLE users ALTER COLUMN execution_policy SET DEFAULT 'require_approval';
UPDATE users SET execution_policy='require_approval' WHERE execution_policy='auto_execute';
```

これは `2026-05-23_backend_codeploy_runbook.md ②-a` の `--sql` 期待出力と一致する。
**3 段目以降が出たら STOP** — 別 PR の未適用 migration が混入している。

---

## 6. Phase E — ロールバック (緊急時のみ)

### E-1. stamp 適用直後・upgrade 未実行の場合

```sql
-- alembic_version テーブルを削除して未 stamp 状態に戻す
DROP TABLE IF EXISTS alembic_version;
```

```bash
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c "DROP TABLE IF EXISTS alembic_version;"
```

DB スキーマ本体は stamp で一切変えていないため、これで完全に元に戻る。

### E-2. C-2 の dry-run と異なる SQL が C-3 で実行された場合

C-1 のバックアップから restore する。`docs/15_rollback_procedures.md` 準拠。

```bash
docker exec -i ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade < /tmp/backup_pre_alembic_stamp_<timestamp>.sql
```

★STOP — restore 後に必ず `2026-05-23_backend_codeploy_runbook.md ⑤` の curl 確認を実行
(scheduler / health / `ai_decisions.max(created_at)`)。

---

## 7. 完了条件

- [ ] `alembic_version` テーブルが production に存在し `version_num = f6a7b8c9d0e1` (または B-1 決定値)
- [ ] dev VPS で `alembic upgrade head --sql f6a7b8c9d0e1:head` が a7 → g7 の 2 段のみを出力
- [ ] バックアップ `/tmp/backup_pre_alembic_stamp_<timestamp>.sql` が S3 オフサイトに同期済み
- [ ] 本 runbook と紐づく Asana タスクに完了コメント (実機 fingerprint 結果 + stamp 値 + upgrade preview の sha256 を添付)
- [ ] `2026-05-23_backend_codeploy_runbook.md ②-a` の起動可否を再評価 (本 runbook 完了後は ②-a の前提が成立)

---

## 8. 既知の論点 (本 runbook では決めず、別途整理)

1. **alembic を production Docker image に同梱するか**
   `CLAUDE.lessons.md 2026-04-05` は alembic を image に含めない方針を明文化している。
   一方 #398 以降の運用では `alembic upgrade head` を deploy フローに組み込みたい。
   本 runbook は dev VPS 側で SQL を生成して production に持ち込む方式で回避するが、
   恒久対応として `backend/requirements.txt` に `alembic` を追加するか別途判断が必要。
   関連 Asana タスクで別 PR を立てる。

2. **`alembic stamp` を deploy_production.sh に組み込むか**
   組み込まない。stamp は一回限りの sync 操作であり、idempotent ではない (既に stamp 済みの
   DB に対して `alembic stamp` を流すと UPDATE になり履歴が消える) ため、明示的な
   one-shot 運用にとどめる。

3. **#398 merge 順序**
   本 runbook の `alembic stamp` は **#398 merge より前でも後でも実行可能**だが、
   推奨は #398 merge 後。理由: #398 merge 前の dev VPS で `alembic upgrade head --sql` を
   流すと multiple heads エラーになり Phase D-2 が実行できない。

---

## 参照

- `CLAUDE.lessons.md:198-213` — 2026-04-05 Hetzner pull only + alembic を image に入れない
- `docs/ops/03_deploy_procedures.md:188-212` — 既存の手動 ALTER TABLE 方式
- `docs/internal/2026-05-23_backend_codeploy_runbook.md` — 本 runbook 完了後に接続する次工程
- PR #398 — `fix(alembic): g7 down_revision を a7 に張り替え、多頭分岐解消 [Tier S]`
- `backend/alembic/versions/*.py` — 各 revision の up_revision 内容
