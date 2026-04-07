#!/usr/bin/env bash
# backup_db.sh — PostgreSQL 日次バックアップ (staging / production 共用)
# Usage: ./scripts/backup_db.sh [--production]
# cron: 0 3 * * * /opt/ultra-autotrade/scripts/backup_db.sh >> /var/log/ultra-autotrade/backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── 環境切り替え ──────────────────────────────────
PRODUCTION=false
for arg in "$@"; do
  [[ "$arg" == "--production" ]] && PRODUCTION=true
done

if "${PRODUCTION}"; then
  CONTAINER_NAME="ultra-autotrade-postgres-production"
  ENV_FILE="${PROJECT_ROOT}/.env.production"
  DB_USER="${POSTGRES_USER:-ultra}"
  DB_NAME="${POSTGRES_DB:-ultra_autotrade}"
else
  CONTAINER_NAME="ultra-autotrade-postgres-staging"
  ENV_FILE="${PROJECT_ROOT}/.env.staging"
  DB_USER="ultra"
  DB_NAME="ultra_autotrade"
fi

BACKUP_DIR="${BACKUP_DIR:-/opt/ultra-autotrade/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/ultra_autotrade_${TIMESTAMP}.sql.gz"

# ── バックアップ実行 ──────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "[${TIMESTAMP}] Starting PostgreSQL backup (container: ${CONTAINER_NAME})..."
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

FILESIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo 0)
echo "✅ Backup created: $BACKUP_FILE ($(( FILESIZE / 1024 )) KB)"

# ── 古いバックアップ削除 ─────────────────────────
find "$BACKUP_DIR" -name "ultra_autotrade_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
echo "🗑️ Old backups cleaned (retention: ${RETENTION_DAYS} days)"

# ── Slack通知（WEBHOOK設定時のみ）────────────────
WEBHOOK=$(grep SLACK_WEBHOOK_URL "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
if [ -n "${WEBHOOK}" ]; then
  curl -sf -X POST "${WEBHOOK}" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"🗄️ [Backup] DB backup completed: $(basename "${BACKUP_FILE}") ($(( FILESIZE / 1024 )) KB)\"}" || true
fi

echo "[${TIMESTAMP}] Backup finished."
