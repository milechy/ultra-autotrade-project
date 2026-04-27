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

### 5.4 Blue/Green 緊急ロールバック (ゼロダウンタイムデプロイ用)

2026-04-27 ゼロダウンタイムデプロイ導入後 (Asana 1214253004741363) 用の
バックエンドコードロールバック手順。新コンテナで問題発生時に旧コンテナへ即座に切り戻す。

前提: deploy_production.sh は切替後に旧コンテナを `stop` のみで保持しているため、
30 秒〜数分以内であれば旧コンテナがそのまま起動可能。

```bash
cd /opt/ultra-autotrade

# 1. 現在 active な slot を判定
ACTIVE=$(grep -oE 'backend-(blue|green)' docker/nginx/upstream.conf | head -1 | sed 's/backend-//')
[ "${ACTIVE}" = "blue" ] && OLD="green" || OLD="blue"
echo "Rolling back from ${ACTIVE} → ${OLD}"

# 2. 旧コンテナを起動 (deploy script が stop で残しているため即座に立つ)
docker compose -f docker-compose.production.yml --env-file .env.production \
  start "backend-${OLD}"

# 3. 旧 slot の host port (blue=8010, green=8011) でヘルスチェック
[ "${OLD}" = "blue" ] && PORT=8010 || PORT=8011
for i in $(seq 1 20); do
  curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null && break
  sleep 1
done

# 4. upstream.conf を旧 slot に書き換え (awk + 一時ファイル + mv、sed -i 禁止)
TMP=$(mktemp docker/nginx/upstream.conf.XXXXXX)
awk -v slot="${OLD}" -v ts="$(date -Iseconds)" 'BEGIN {
  printf "# Manual rollback at %s\n", ts
  printf "# Active slot: %s\n", slot
  printf "server backend-%s:8000 max_fails=3 fail_timeout=10s;\n", slot
}' </dev/null > "${TMP}"
mv "${TMP}" docker/nginx/upstream.conf

# 5. nginx reload (ゼロダウンタイム保証)
docker exec ultra-autotrade-nginx-production nginx -s reload

# 6. 切替確認
curl -sf http://localhost:8080/health | python3 -m json.tool
```

**コードロールバックが旧コンテナで足りない場合 (例: 旧コンテナも消失)**:

1. Git で前回タグへロールバック:
   ```bash
   git checkout v<previous-tag>
   ./scripts/deploy_production.sh   # フルデプロイで blue を再構築
   ```
2. 設計詳細: `docs/19_operations_runbook.md §3.4 緊急ロールバック (Blue/Green)`

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
