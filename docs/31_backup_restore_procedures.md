# バックアップ・リストア手順

## 1. バックアップ対象

| 対象 | 方法 | 頻度 | 保持期間 |
|---|---|---|---|
| PostgreSQL | pg_dump | 日次 | 30日 |
| state.json | ファイルコピー | 日次 | 30日 |
| .env.production | ファイルコピー | 変更時 | 永久 |

> **セキュリティ注意** (`docs/13_security_design.md §10`):
> バックアップファイルは暗号化ストレージに保存し、Git や共有ストレージに平文で置かないこと。

---

## 2. PostgreSQL バックアップ

### 自動バックアップスクリプト

```bash
scripts/backup_db.sh
```

詳細は [scripts/backup_db.sh](../scripts/backup_db.sh) を参照。

### cron 設定（Hetzner VPS 上で設定）

```
0 0 * * * /opt/ultra-autotrade/scripts/backup_db.sh >> /var/log/ultra-autotrade/backup.log 2>&1
```

設定方法:

```bash
crontab -e
# 上記の行を追加して保存
```

---

## 3. state.json バックアップ

MonitoringService が使用する `state.json` を日次でコピーする。

```bash
#!/bin/bash
# scripts/backup_state.sh 内の処理（backup_db.sh に統合済み）
BACKUP_DIR="/opt/ultra-autotrade/backups/state"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
STATE_FILE="/opt/ultra-autotrade/backend/state.json"

mkdir -p "$BACKUP_DIR"

if [ -f "$STATE_FILE" ]; then
  cp "$STATE_FILE" "$BACKUP_DIR/state_${TIMESTAMP}.json"
  find "$BACKUP_DIR" -name "state_*.json" -mtime +30 -delete
  echo "state.json backup completed: state_${TIMESTAMP}.json"
else
  echo "WARNING: state.json not found at $STATE_FILE"
fi
```

---

## 4. .env.production バックアップ

```bash
# 変更後に手動で実行
BACKUP_DIR="/opt/ultra-autotrade/backups/env"
mkdir -p "$BACKUP_DIR"
cp /opt/ultra-autotrade/.env.production "$BACKUP_DIR/.env.production.$(date +%Y%m%d)"
chmod 600 "$BACKUP_DIR/.env.production.$(date +%Y%m%d)"
```

> **注意**: `.env.production` には秘密鍵・APIキーが含まれるため、
> バックアップ先のディレクトリはアクセス権を `700` 以下に制限すること。

---

## 5. リストア手順

### PostgreSQL リストア

```bash
# バックアップファイルを指定してリストア
gunzip -c /opt/ultra-autotrade/backups/db/ultra_autotrade_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose -f /opt/ultra-autotrade/docker-compose.production.yml exec -T postgres \
  psql -U ultra_user ultra_autotrade
```

> **注意**: リストア前に既存データが上書きされる。必要に応じて先に別名でバックアップを取ること。

### state.json リストア

```bash
cp /opt/ultra-autotrade/backups/state/state_YYYYMMDD_HHMMSS.json \
   /opt/ultra-autotrade/backend/state.json

docker compose -f /opt/ultra-autotrade/docker-compose.production.yml restart backend
```

### .env.production リストア

```bash
# リストア後は必ずキーの有効期限・staging混入がないか確認すること
cp /opt/ultra-autotrade/backups/env/.env.production.YYYYMMDD \
   /opt/ultra-autotrade/.env.production

# docs/13_security_design.md §10.2 のチェックリストを実施
```

---

## 6. リストア後の検証

```bash
# 1. ヘルスチェック
curl http://localhost:8000/health

# 2. AI判定履歴の件数確認
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml exec postgres \
  psql -U ultra_user ultra_autotrade -c "SELECT count(*) FROM ai_decisions;"

# 3. ユーザー存在確認
docker compose -f /opt/ultra-autotrade/docker-compose.production.yml exec postgres \
  psql -U ultra_user ultra_autotrade -c "SELECT count(*) FROM users;"

# 4. Emergency stop フラグの確認（state.json）
cat /opt/ultra-autotrade/backend/state.json | python3 -m json.tool | grep emergency
```

---

## 7. バックアップディレクトリ構成

```
/opt/ultra-autotrade/backups/
├── db/
│   ├── ultra_autotrade_20260101_000000.sql.gz
│   └── ultra_autotrade_20260102_000000.sql.gz
├── state/
│   ├── state_20260101_000000.json
│   └── state_20260102_000000.json
└── env/
    ├── .env.production.20260101
    └── .env.production.20260115
```

---

## 関連ドキュメント

- `docs/13_security_design.md §10` — バックアップ時のセキュリティ要件
- `docs/19_operations_runbook.md` — インシデント対応手順
- `docs/21_production_environment_config.md` — 環境変数リスト
- `docs/22_production_release_checklist.md` — リリース前チェックリスト
