# Backup / Restore Runbook (P0-1)

> **Scope:** 実機 DR drill 用 step-by-step runbook。設計・仕組みの全体像は `docs/31_backup_restore_procedures.md` を参照。本 runbook は **「実際に何を打ち、何を見て、何件 OK なら合格か」** にのみ集中する。
>
> **Related Asana:** P0-1 (Backup 復元検証 — prod DB / .env / wallet 鍵)
> **Owner:** On-call engineer
> **Cadence:** 月次 (production restore drill)、変更時 (.env / wallet)
> **Data loss tolerance:** **24h** (前日 03:00 のバックアップまで戻る可能性を ToS 同意 — P0-3 / P0-13 と整合)

---

## 0. Prerequisites

| 項目 | チェック |
|---|---|
| `backup_db.sh` が cron で動いている | `crontab -l \| grep backup_db` |
| `db_backups/` に直近 24h のファイルがある | `ls -lh /opt/ultra-autotrade/db_backups/production_*.sql.gz \| tail -3` |
| 月次アーカイブが今月分ある | `ls /opt/ultra-autotrade/db_backups/monthly/` |
| Wallet 鍵バックアップが暗号化保管されている | §3 参照 |
| Restore 先環境が用意できる (staging or scratch DB) | §1 参照 |

> **本 runbook は production を壊さない。** 必ず scratch DB / staging で実機検証する。

---

## 1. PostgreSQL Restore Drill

### 1.1 復元先 (scratch) を準備

```bash
# staging-new の DB に restore する場合（破壊的: staging-new が一時的に上書きされる）
SCRATCH_CONTAINER="postgres-staging"
SCRATCH_DB="ultra_autotrade_staging_restore_drill"
docker exec "${SCRATCH_CONTAINER}" \
  psql -U ultra -c "CREATE DATABASE ${SCRATCH_DB};"
```

期待出力: `CREATE DATABASE`

### 1.2 最新バックアップを選ぶ

```bash
LATEST=$(ls -1t /opt/ultra-autotrade/db_backups/production_ultra_autotrade_*.sql.gz | head -1)
echo "Restoring: ${LATEST}"
```

### 1.3 gzip 整合性を pre-flight

```bash
gzip -t "${LATEST}" && echo "✅ gzip OK" || echo "❌ corrupted"
```

期待出力: `✅ gzip OK`

### 1.4 Restore 実行

```bash
gunzip -c "${LATEST}" | \
  docker exec -i "${SCRATCH_CONTAINER}" psql -U ultra "${SCRATCH_DB}"
```

期待: 末尾近くで `ALTER TABLE`/`COPY` 等が並び、エラー行なし。`psql:.*ERROR` が 0 件。

### 1.5 検証チェックリスト

| # | クエリ | 期待値 (production-like) |
|---|---|---|
| 1 | `SELECT count(*) FROM users;` | > 0、本番件数 ±5% |
| 2 | `SELECT count(*) FROM ai_decisions;` | > 0 |
| 3 | `SELECT max(created_at) FROM ai_decisions;` | 直近 24h 以内 |
| 4 | `SELECT count(*) FROM proposals WHERE status='applied';` | > 0 |
| 5 | `SELECT version_num FROM alembic_version;` | production と同一 head |
| 6 | `SELECT count(*) FROM tos_consents;` (W1-12 後) | > 0 |

全件 OK で **「Restore drill PASS」**。NG 1件でも escalation (§5)。

### 1.6 後始末

```bash
docker exec "${SCRATCH_CONTAINER}" \
  psql -U ultra -c "DROP DATABASE ${SCRATCH_DB};"
```

---

## 2. `.env.production` Restore

> **危険度: 高。** 鍵差し替えのため必ず docker 再起動を伴う。

### 2.1 バックアップから復元する場合

```bash
BACKUP=/opt/ultra-autotrade/backups/env/.env.production.YYYYMMDD
diff /opt/ultra-autotrade/.env.production "${BACKUP}" | head -50
```

差分を目視で確認。**rotate 対象のキー (private key, slack webhook, RPC URL) が差分にあれば停止し §5 escalate**。

### 2.2 復元 + 整合性チェック

```bash
cp "${BACKUP}" /opt/ultra-autotrade/.env.production
chmod 600 /opt/ultra-autotrade/.env.production

# staging と prod の鍵が同一なら即停止 (CLAUDE.md security rule #7)
grep -E '^(PRIVATE_KEY|PROD_PRIVATE_KEY)=' /opt/ultra-autotrade/.env.production > /tmp/prod_keys
grep -E '^(PRIVATE_KEY|STAGING_PRIVATE_KEY)=' /opt/ultra-autotrade/.env.staging-new 2>/dev/null > /tmp/stg_keys
if diff -q /tmp/prod_keys /tmp/stg_keys >/dev/null 2>&1; then
  echo "❌ STAGING と PROD の鍵が一致。即 §5 escalate"; exit 1
fi
```

### 2.3 反映

```bash
cd /opt/ultra-autotrade
docker compose -f docker-compose.production.yml --env-file .env.production up -d
curl -sf http://localhost:8000/health | python3 -m json.tool
```

期待: `status: "ok"`

---

## 3. Wallet 鍵リストア

> **本セクションは P0-17 (Operator wallet 確保 + 鍵管理) と密結合。**
> 鍵そのものは backup_db.sh の対象外。物理 (HW wallet / encrypted vault) で別管理。

### 3.1 鍵保管場所 (3 拠点)

| 拠点 | 媒体 | 暗号 | 復号鍵保管 |
|---|---|---|---|
| プライマリ | HW wallet #1 | デバイス標準 | Owner physical |
| セカンダリ | Encrypted vault (cloud) | age + passphrase | Recovery sheet |
| 紙バックアップ | Steel plate | mnemonic 24 words | Bank safe deposit |

詳細は `docs/ops/signer_runbook.md` (W0-5) と P0-17.3 ハードキー手順書。

### 3.2 Restore 手順 (HW wallet 紛失時)

1. **Slack #ops に "WALLET LOSS" 宣言**、Owner 召集 (24h 以内)
2. プライマリ侵害判定: Etherscan で operator wallet の最近 7 日 tx を確認 → 不審 tx あれば即 emergency_stop 強制 (§4)
3. セカンダリ → age 復号 → 新 HW wallet に import
4. (3 of N multisig 構成) 残 signer 2人で operator address rotate (Safe multisig)
5. `.env.production` の `OPERATOR_WALLET_ADDRESS` を新 address に更新 → §2 で反映
6. 旧 address からの引き出しを禁止リストに追加

> **絶対禁止**: 復元した秘密鍵を `.env` に書く前に Slack / Notion / GitHub にコピペすること。`pbcopy` / `xclip` も使わない (clipboard 漏洩経路)。

---

## 4. Emergency Stop (リストア中の事故対応)

リストア中に異常発見 (鍵流出疑い / 不正 tx / DB 破損疑い):

```bash
# 1. backend を即停止
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml stop backend-blue backend-green

# 2. state.json の emergency_stop フラグを ON (OR-logic で復帰されない)
python3 -c "
import json, pathlib
p = pathlib.Path('/opt/ultra-autotrade/backend/state.json')
d = json.loads(p.read_text())
d['emergency_stop'] = True
d['emergency_stop_reason'] = 'restore-drill-anomaly-$(date -Iseconds)'
p.write_text(json.dumps(d, indent=2))
print('emergency_stop = True')
"

# 3. Slack に Tier S 通知
curl -sf -X POST "$(grep ^SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | cut -d= -f2-)" \
  -H "Content-Type: application/json" \
  -d '{"text":"🚨 [Tier S] backup_restore drill aborted — emergency_stop ON. See §5 escalation."}'
```

---

## 5. Escalation

| 重大度 | 条件 | 通知先 | SLA |
|---|---|---|---|
| Tier S | 鍵流出疑い / 不正 tx 検出 / 24h以上のデータ損失 | Owner phone (B-2 経路) + Slack #ops | 15 min |
| Tier A | gzip 整合性失敗 / restore drill 失敗 / バックアップ不在 24h+ | Slack #ops | 1 h |
| Tier B | 月次アーカイブ抜け / retention violation | Slack #ops daily summary | 翌営業日 |

---

## 6. Recovery Point / Time Objectives

| 項目 | 目標 | 現状 (2026-05) |
|---|---|---|
| **RPO** (最大データ損失) | 24h | 24h ✅ (日次 03:00 backup) |
| **RTO** (復旧時間) | 1h | drill 未計測 → 本 runbook で計測 |
| Backup 検証カバー率 | 100% | scripts/backup_db.sh 自動検証 ✅ |
| Restore drill 実施頻度 | 月次 | 未確立 → 本 runbook 化で開始 |

---

## 7. Drill Log

| 実施日 | Restore PASS? | RTO 実測 | 担当 | 備考 |
|---|---|---|---|---|
| (template) 2026-MM-DD | ✅/❌ | XX min | name | 検証 SQL 6/6 |

---

## 参照

- `docs/31_backup_restore_procedures.md` — 全体設計
- `docs/13_security_design.md §10` — backup security
- `docs/ops/signer_runbook.md` — wallet 鍵運用 (W0-5)
- `docs/ops/production_operation_checklist.md` — リリース時 backup 確認
- `scripts/backup_db.sh` — env-aware backup スクリプト
