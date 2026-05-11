# 2026-05-11 — PR #182 `users_auth_method_check` production 反映 + backup_db.sh env-aware 化

- Session: 5
- Asana: GID 1214176336328111 (PR #182) / GID 1214700856891960 (backup_db.sh env-aware)
- PR (本作業): claude/pr182-backup-env-aware-mGg18 → main
- 関連 PR: #182 (`feature/auth-hashed-privy-exclusive-check` → main)
- 期日: 2026-05-11 11:00 JST

## サマリ

PR #182 で導入された Alembic migration `a0b1c2d3e4f5`（`users.hashed_password` を nullable
化 + `users_auth_method_check` CHECK 制約追加）は staging-new に 2026-05-02 に適用済みだが、
9 日間 production 未適用のまま放置されていた。Privy-only ユーザーをサポートする F-17/L1
（`POST /auth/wallet/link`、PR #207）が main 反映済みのため、production 側の users テーブル
スキーマと backend モデル定義 (`Mapped[Optional[str]] = mapped_column(..., nullable=True)`)
が乖離している。本作業で同 2 段 ALTER を production に適用する。

並行して `scripts/backup_db.sh` の `--production` フラグ式を `ENVIRONMENT` 環境変数式へ移行し、
staging-new コンテナ名 (`ultra-autotrade-postgres-staging-new`) を実態に合わせ、
`deploy_staging.sh` のフルデプロイ時にも自動 backup を取得する。

## production ALTER 内容

```sql
BEGIN;
ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;
ALTER TABLE users ADD CONSTRAINT users_auth_method_check
    CHECK (hashed_password IS NOT NULL OR privy_did IS NOT NULL);

-- 検証
SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='users_auth_method_check';
SELECT column_name, is_nullable FROM information_schema.columns
 WHERE table_name='users' AND column_name='hashed_password';
COMMIT;
```

PR #182 migration `a0b1c2d3e4f5` の `upgrade()` と完全に同一。staging-new と
spec が一致することを保証する。

## 事前確認 (Pre-check)

### 違反レコード SELECT — 必ず 0 件であること

```sql
SELECT id, username, hashed_password IS NULL AS no_hash, privy_did IS NULL AS no_privy
  FROM users
 WHERE hashed_password IS NULL
   AND privy_did IS NULL;
```

0 件以外なら ALTER 中止 → 違反レコードの調査 → 別 PR で対応。

### pg_dump バックアップ

```bash
SSH_OPTS="-i ~/.ssh/hetzner_staging"
ssh $SSH_OPTS ultra@77.42.46.155 \
  "cd /opt/ultra-autotrade && git pull origin main && \
   ENVIRONMENT=production bash scripts/backup_db.sh"
# 期待出力: /opt/ultra-autotrade/db_backups/production_ultra_autotrade_YYYYMMDD_HHMMSS.sql.gz
```

## ロールバック手順 (RTO < 2 分)

### 条件
- ALTER 適用後 5 分以内に `/health` が `degraded` を返す
- backend ログに `users_auth_method_check` IntegrityError が継続出現
- production users テーブルへの INSERT が想定外に失敗

### 実行 SQL

```sql
BEGIN;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_auth_method_check;
ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL;
COMMIT;
```

**注意:** `SET NOT NULL` は既存 NULL 行があると失敗する。Privy-only ユーザーが既に作成済みの
場合は先に該当行を確認 → `SET NOT NULL` を諦め、`DROP CONSTRAINT` のみ実行する。

### フル復元（最後の手段）

backup ファイルから物理復元:
```bash
ssh $SSH_OPTS ultra@77.42.46.155 \
  "gunzip -c /opt/ultra-autotrade/db_backups/production_ultra_autotrade_<TS>.sql.gz | \
   docker exec -i ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade"
```

## デプロイ後検証 (Gate 8)

```bash
# 5 分連続 healthcheck
for i in {1..30}; do
  curl -fsS -o /dev/null -w "%{http_code} %{time_total}s\n" https://api.ultra-auto-trade.com/health
  sleep 10
done

# scheduler_healthy 確認
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool

# CHECK 制約適用確認
ssh $SSH_OPTS ultra@77.42.46.155 \
  "docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
    \"SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='users_auth_method_check';\""

# backend ログに IntegrityError が出ていないこと
ssh $SSH_OPTS ultra@77.42.46.155 \
  "docker logs --tail=300 ultra-autotrade-backend-blue-production 2>&1 | \
   grep -E 'IntegrityError|users_auth_method_check' | head"
```

## backup_db.sh 変更内容

| 項目 | Before | After |
|---|---|---|
| 切替 | `--production` フラグ | `ENVIRONMENT=production\|staging-new` 環境変数（フラグ後方互換あり） |
| staging コンテナ名 | `ultra-autotrade-postgres-staging`（**古い名前、実環境と不一致**） | `ultra-autotrade-postgres-staging-new` |
| staging DB 名 | `ultra_autotrade` | `ultra_autotrade_staging` |
| BACKUP_DIR デフォルト | `/opt/ultra-autotrade/backups` | `/opt/ultra-autotrade/db_backups` |
| ファイル名 prefix | `ultra_autotrade_<TS>.sql.gz` | `<env>_ultra_autotrade_<TS>.sql.gz` |
| 不正 ENVIRONMENT | （未検証） | `exit 1` + エラーメッセージ |
| `deploy_staging.sh` からの呼び出し | 未配線 | フルデプロイ時に自動実行 |
| `deploy_production.sh` からの呼び出し | フルデプロイ時のみ（`bash backup_db.sh`） | フルデプロイ時のみ（`ENVIRONMENT=production bash backup_db.sh`、明示化） |

## 教訓

1. **migration 適用は環境間で水平展開を完了させること。** PR #182 は staging-new 適用後 9 日間
   production 未適用のまま放置された。CLAUDE.md L1042 §2026-05-09 教訓 4「production と
   同型のインフラインシデント / migration は staging へ水平展開を PR description に必須記述」
   と同じパターン。今後は migration PR の Test plan に「production 反映チケット」を必須化する。

2. **backup スクリプトはコンテナ名リネーム時に追従させる。** `staging` → `staging-new` の
   container_name 変更（2026-04-17）から 1 ヶ月以上、`backup_db.sh` の staging 分岐が
   不在コンテナを参照したまま放置されていた。インフラ変更チェックリスト
   (CLAUDE.md L1004-L1011 「インフラ変更前チェックリスト」) に「backup スクリプトの参照を
   確認」を追加する。

3. **deploy_staging.sh にも pre-deploy backup を配線。** production だけでなく staging-new も
   フルデプロイ前に backup を取得することで、staging のデプロイ起因事故を防止できる。
