#!/usr/bin/env bash
# backup_db.sh — PostgreSQL 日次バックアップ (production / staging-new 切替)
# 自己検証機能: バックアップ後にファイルサイズ + gzip 整合性を検証。
#               失敗時は Slack #ultra-auto-project に通知して exit 1。
#               (RC-4 Asana GID 1214882070742107)
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
    CONTAINER_FILTER="postgres-production"
    ENV_FILE="${PROJECT_ROOT}/.env.production"
    DB_NAME="ultra_autotrade"
    ;;
  staging-new)
    CONTAINER_FILTER="postgres-staging"
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
MIN_SIZE_BYTES="${MIN_SIZE_BYTES:-10240}"   # 10 KB 未満は異常とみなす
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${ENVIRONMENT}_ultra_autotrade_${TIMESTAMP}.sql.gz"

# ── Slack 通知ヘルパー ─────────────────────────────
_slack_send() {
  local text="$1"
  local webhook
  webhook="$(grep '^SLACK_WEBHOOK_URL=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)"
  if [ -n "${webhook}" ]; then
    curl -sf -X POST "${webhook}" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"${text}\"}" || true
  fi
}

# ── 失敗通知 + クリーンアップ ──────────────────────
_notify_failure() {
  local reason="$1"
  echo "❌ [${ENVIRONMENT}] Backup FAILED: ${reason}" >&2
  _slack_send "❌ [${ENVIRONMENT}] backup_db.sh FAILED: ${reason}"
  rm -f "${BACKUP_FILE}" 2>/dev/null || true
}

# ERR トラップ: pg_dump 失敗等の予期しないエラーも Slack 通知する
trap '_notify_failure "unexpected error at line ${LINENO} (exit $?)"' ERR

# ── コンテナ名の動的取得 (ハードコード禁止 / RC-4) ──
CONTAINER_NAME="$(docker ps --filter "name=${CONTAINER_FILTER}" --filter "status=running" \
  --format "{{.Names}}" | head -1)"
if [ -z "${CONTAINER_NAME}" ]; then
  # ERR トラップを外してから手動で通知 (トラップのネストを避ける)
  trap - ERR
  echo "ERROR: [${ENVIRONMENT}] postgres コンテナが起動していません (filter: ${CONTAINER_FILTER})" >&2
  _slack_send "❌ [${ENVIRONMENT}] backup_db.sh: postgres コンテナ未起動 (filter: ${CONTAINER_FILTER})"
  exit 1
fi

# ── バックアップ実行 ──────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "[${TIMESTAMP}] [${ENVIRONMENT}] Starting PostgreSQL backup (container: ${CONTAINER_NAME}, db: ${DB_NAME})..."
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

# ── 自己検証 1: ファイルサイズ ───────────────────
FILESIZE="$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo 0)"
if [ "${FILESIZE}" -lt "${MIN_SIZE_BYTES}" ]; then
  _notify_failure "file too small: ${FILESIZE} bytes (minimum: ${MIN_SIZE_BYTES})"
  exit 1
fi

# ── 自己検証 2: gzip 整合性 ──────────────────────
if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
  _notify_failure "gzip integrity check failed (corrupted archive)"
  exit 1
fi

# 検証完了後は ERR トラップを解除（クリーンアップ失敗で誤通知しない）
trap - ERR

echo "✅ [${ENVIRONMENT}] Backup verified: ${BACKUP_FILE} ($(( FILESIZE / 1024 )) KB, gzip OK)"

# ── 古いバックアップ削除 (同じ ENVIRONMENT のものだけ) ──
find "$BACKUP_DIR" -maxdepth 1 -name "${ENVIRONMENT}_ultra_autotrade_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
echo "🗑️ [${ENVIRONMENT}] Old backups cleaned (retention: ${RETENTION_DAYS} days)"

# ── Slack 成功通知（WEBHOOK設定時のみ）───────────
_slack_send "🗄️ [${ENVIRONMENT}] DB backup completed: $(basename "${BACKUP_FILE}") ($(( FILESIZE / 1024 )) KB)"

echo "[${TIMESTAMP}] [${ENVIRONMENT}] Backup finished."
