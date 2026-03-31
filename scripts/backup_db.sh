#!/usr/bin/env bash
# backup_db.sh — PostgreSQL + state.json の日次バックアップ
# Usage: ./scripts/backup_db.sh
# cron: 0 0 * * * /opt/ultra-autotrade/scripts/backup_db.sh >> /var/log/ultra-autotrade/backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKUP_BASE="${BACKUP_BASE:-${PROJECT_ROOT}/backups}"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.production.yml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

DB_BACKUP_DIR="${BACKUP_BASE}/db"
STATE_BACKUP_DIR="${BACKUP_BASE}/state"
STATE_FILE="${PROJECT_ROOT}/backend/state.json"

POSTGRES_USER="${POSTGRES_USER:-ultra_user}"
POSTGRES_DB="${POSTGRES_DB:-ultra_autotrade}"

# ---- PostgreSQL バックアップ ----
mkdir -p "$DB_BACKUP_DIR"

echo "[${TIMESTAMP}] Starting PostgreSQL backup..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "${DB_BACKUP_DIR}/ultra_autotrade_${TIMESTAMP}.sql.gz"

echo "[${TIMESTAMP}] PostgreSQL backup completed: ultra_autotrade_${TIMESTAMP}.sql.gz"

# 30日より古いバックアップを削除
find "$DB_BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete

# ---- state.json バックアップ ----
mkdir -p "$STATE_BACKUP_DIR"

if [ -f "$STATE_FILE" ]; then
  cp "$STATE_FILE" "${STATE_BACKUP_DIR}/state_${TIMESTAMP}.json"
  echo "[${TIMESTAMP}] state.json backup completed: state_${TIMESTAMP}.json"
  find "$STATE_BACKUP_DIR" -name "state_*.json" -mtime +30 -delete
else
  echo "[${TIMESTAMP}] WARNING: state.json not found at ${STATE_FILE}, skipping."
fi

echo "[${TIMESTAMP}] Backup finished."
