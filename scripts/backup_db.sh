#!/usr/bin/env bash
# backup_db.sh — PostgreSQL 日次バックアップ (production / staging-new 切替)
#
# Usage:
#   ENVIRONMENT=production    bash scripts/backup_db.sh
#   ENVIRONMENT=staging-new   bash scripts/backup_db.sh
#   bash scripts/backup_db.sh --production    # 後方互換
#   bash scripts/backup_db.sh --staging-new   # 後方互換
#
# cron (production):
#   0 3 * * * ENVIRONMENT=production /opt/ultra-autotrade/scripts/backup_db.sh >> /var/log/ultra-autotrade/backup.log 2>&1
#
# Asana GID 1214700856891960 (env-aware 化)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── 環境切り替え ──────────────────────────────────
ENVIRONMENT="${ENVIRONMENT:-}"
for arg in "$@"; do
  case "$arg" in
    --production)             ENVIRONMENT="production" ;;
    --staging|--staging-new)  ENVIRONMENT="staging-new" ;;
  esac
done
# default = production (CLAUDE.md production-first 原則)
ENVIRONMENT="${ENVIRONMENT:-production}"

case "$ENVIRONMENT" in
  production)
    CONTAINER_NAME="ultra-autotrade-postgres-production"
    ENV_FILE="${PROJECT_ROOT}/.env.production"
    DB_NAME="ultra_autotrade"
    ;;
  staging-new)
    CONTAINER_NAME="ultra-autotrade-postgres-staging-new"
    ENV_FILE="${PROJECT_ROOT}/.env.staging-new"
    DB_NAME="ultra_autotrade_staging"
    ;;
  *)
    echo "ERROR: ENVIRONMENT must be 'production' or 'staging-new' (got: '${ENVIRONMENT}')" >&2
    exit 1
    ;;
esac

DB_USER="${POSTGRES_USER:-ultra}"
BACKUP_DIR="${BACKUP_DIR:-/opt/ultra-autotrade/db_backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${ENVIRONMENT}_ultra_autotrade_${TIMESTAMP}.sql.gz"

# ── バックアップ実行 ──────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "[${TIMESTAMP}] [${ENVIRONMENT}] Starting PostgreSQL backup (container: ${CONTAINER_NAME}, db: ${DB_NAME})..."
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

FILESIZE="$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo 0)"
echo "✅ [${ENVIRONMENT}] Backup created: ${BACKUP_FILE} ($(( FILESIZE / 1024 )) KB)"

# ── 古いバックアップ削除 (同じ ENVIRONMENT のものだけ) ──
find "$BACKUP_DIR" -maxdepth 1 -name "${ENVIRONMENT}_ultra_autotrade_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
echo "🗑️ [${ENVIRONMENT}] Old backups cleaned (retention: ${RETENTION_DAYS} days)"

# ── Slack通知（WEBHOOK設定時のみ）────────────────
WEBHOOK="$(grep '^SLACK_WEBHOOK_URL=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)"
if [ -n "${WEBHOOK}" ]; then
  curl -sf -X POST "${WEBHOOK}" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"🗄️ [${ENVIRONMENT}] DB backup completed: $(basename "${BACKUP_FILE}") ($(( FILESIZE / 1024 )) KB)\"}" || true
fi

echo "[${TIMESTAMP}] [${ENVIRONMENT}] Backup finished."
