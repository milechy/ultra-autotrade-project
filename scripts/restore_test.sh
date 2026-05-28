#!/usr/bin/env bash
# restore_test.sh — backup ファイルを一時 DB に restore して整合性確認する dry-run スクリプト
#
# 目的:
#   災害復旧 (本番 DB / staging DB 復元) に先立ち、backup ファイルが
#   正常に restore できることを「本番に触らずに」検証する。
#
# 関連:
#   - 生成元 backup: scripts/backup_db.sh (pg_dump | gzip → .sql.gz)
#   - 災害復旧手順: docs/ops/restore_runbook.md
#   - Asana 本番運用: MVP-P0-1 Backup 復元検証 (prod DB / .env / wallet 鍵)
#
# Usage:
#   ./scripts/restore_test.sh --backup-file=/path/to/backup.sql.gz
#   ./scripts/restore_test.sh --backup-file=... --env=staging
#   ./scripts/restore_test.sh --backup-file=... --temp-db-name=restore_test_custom
#   ./scripts/restore_test.sh --backup-file=... --keep-temp-db
#   ./scripts/restore_test.sh --help
#
# 安全装置:
#   - 本番 DB / staging DB に絶対に書き込まない。CREATE/DROP は一時 DB 名のみ。
#   - 一時 DB 名は restore_test_ プレフィックス必須 (他名は拒否)。
#   - DATABASE_URL は読まない。一時 DB 専用接続情報を組み立てる。
#   - --env は形だけの目印 (表示用) で、実 DB には接続しない。
#
# Exit codes:
#   0 -- restore OK + 整合性 OK
#   1 -- restore 失敗 or 整合性 NG
#   2 -- 設定エラー (引数不正 / backup file 不存在 / 一時 DB 作成失敗)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC2034  # reserved for future use (relative path resolution)
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── デフォルト値 ────────────────────────────────────────────────
BACKUP_FILE=""
ENV_TARGET="staging"
TEMP_DB_NAME=""
KEEP_TEMP_DB=0

# 一時 DB 名のプレフィックス (安全装置: 他プレフィックスの DB に対する DROP/CREATE を拒否)
TEMP_DB_PREFIX="restore_test_"

# 検証時に「最低 1 件以上 row が期待される」テーブル群
# (空 DB を誤って backup した場合に検出するため。
#  ただし新規 staging 等 row が無い場合もあるので、警告扱いに留める)
EXPECTED_TABLES=(
  "users"
  "ai_decisions"
  "proposals"
  "transactions"
  "portfolio_snapshots"
  "fund_allocations"
  "fee_transactions"
  "alembic_version"
)

# ── ログ ────────────────────────────────────────────────────────
log()  { echo "[restore-test] $*"; }
warn() { echo "[restore-test][WARN] $*" >&2; }
err()  { echo "[restore-test][ERROR] $*" >&2; }

# ── help ────────────────────────────────────────────────────────
print_help() {
  # 先頭の連続するコメント行 (shebang を除く) だけを抽出して表示する
  awk '
    NR==1 && /^#!/ { next }
    /^#/           { sub(/^# ?/,""); print; next }
    { exit }
  ' "$0"
  cat <<'EOF'

Arguments:
  --backup-file=<path>    (required) restore する backup ファイル (.sql.gz / .sql / pg_dump custom format)
  --env=<staging|production>
                          (default: staging) backup 元環境ラベル (表示用のみ。実 DB には接続しない)
  --temp-db-name=<name>   (default: restore_test_<timestamp>) 検証用一時 DB 名
                          ※ "restore_test_" プレフィックス必須
  --keep-temp-db          (default: false) 検証後に一時 DB を残す (調査用)
  --help                  このヘルプを表示

Environment variables:
  RESTORE_TEST_PG_HOST    PostgreSQL ホスト (default: localhost)
  RESTORE_TEST_PG_PORT    PostgreSQL ポート (default: 5432)
  RESTORE_TEST_PG_USER    PostgreSQL ユーザ (default: postgres)
  RESTORE_TEST_PG_CONTAINER
                          docker exec 経由で実行する場合のコンテナ名
                          (未設定なら host の psql/pg_restore を使用)

Examples:
  # 最小実行
  ./scripts/restore_test.sh --backup-file=/tmp/staging_backup.sql.gz

  # 本番 backup の検証 (env ラベルのみ。実 DB には接続しない)
  ./scripts/restore_test.sh \
    --backup-file=/opt/ultra-autotrade/db_backups/production_ultra_autotrade_20260527_030000.sql.gz \
    --env=production

  # docker postgres コンテナを使う
  RESTORE_TEST_PG_CONTAINER=ultra-autotrade-postgres-staging-new \
    ./scripts/restore_test.sh --backup-file=/tmp/backup.sql.gz
EOF
}

# ── 引数パース ──────────────────────────────────────────────────
for arg in "$@"; do
  case "${arg}" in
    --backup-file=*)  BACKUP_FILE="${arg#--backup-file=}" ;;
    --env=*)          ENV_TARGET="${arg#--env=}" ;;
    --temp-db-name=*) TEMP_DB_NAME="${arg#--temp-db-name=}" ;;
    --keep-temp-db)   KEEP_TEMP_DB=1 ;;
    --help|-h)        print_help; exit 0 ;;
    *)
      err "Unknown argument: ${arg}"
      err "Run with --help for usage."
      exit 2
      ;;
  esac
done

# ── バリデーション ──────────────────────────────────────────────
if [[ -z "${BACKUP_FILE}" ]]; then
  err "--backup-file=<path> is required."
  err "Run with --help for usage."
  exit 2
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  err "backup file not found: ${BACKUP_FILE}"
  exit 2
fi

case "${ENV_TARGET}" in
  staging|production) ;;
  *)
    err "--env must be 'staging' or 'production' (got: '${ENV_TARGET}')"
    exit 2
    ;;
esac

# 一時 DB 名のデフォルト + プレフィックス強制
if [[ -z "${TEMP_DB_NAME}" ]]; then
  TEMP_DB_NAME="${TEMP_DB_PREFIX}$(date +%Y%m%d_%H%M%S)_$$"
fi

if [[ "${TEMP_DB_NAME}" != ${TEMP_DB_PREFIX}* ]]; then
  err "--temp-db-name must start with '${TEMP_DB_PREFIX}' (got: '${TEMP_DB_NAME}')"
  err "This is a safety guard to prevent accidental CREATE/DROP on production DBs."
  exit 2
fi

# 一時 DB 名は本番 / staging の既知 DB 名と被ってはならない (二重ガード)
case "${TEMP_DB_NAME}" in
  ultra_autotrade|ultra_autotrade_staging|postgres|template0|template1)
    err "--temp-db-name collides with a reserved/known DB name: ${TEMP_DB_NAME}"
    exit 2
    ;;
esac

# ── backup file sanity check ────────────────────────────────────
BACKUP_SIZE="$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null || echo 0)"
if [[ "${BACKUP_SIZE}" -le 0 ]]; then
  err "backup file is empty (0 bytes): ${BACKUP_FILE}"
  exit 2
fi

BACKUP_FILE_BASENAME="$(basename "${BACKUP_FILE}")"
BACKUP_FORMAT=""
case "${BACKUP_FILE_BASENAME}" in
  *.sql.gz)
    BACKUP_FORMAT="sql.gz"
    # gzip integrity 確認
    if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
      err "gzip integrity check failed: ${BACKUP_FILE}"
      exit 2
    fi
    ;;
  *.sql)
    BACKUP_FORMAT="sql"
    ;;
  *.dump|*.pgdump|*.custom)
    BACKUP_FORMAT="custom"
    ;;
  *)
    warn "Unknown backup file extension: ${BACKUP_FILE_BASENAME}"
    warn "Assuming plain SQL format. Use --help for supported formats."
    BACKUP_FORMAT="sql"
    ;;
esac

# ── PostgreSQL 接続情報 (一時 DB 用、本番 DB には触らない) ──────
PG_HOST="${RESTORE_TEST_PG_HOST:-localhost}"
PG_PORT="${RESTORE_TEST_PG_PORT:-5432}"
PG_USER="${RESTORE_TEST_PG_USER:-postgres}"
PG_CONTAINER="${RESTORE_TEST_PG_CONTAINER:-}"

# psql / pg_restore のラッパー (docker exec or host)
_psql() {
  if [[ -n "${PG_CONTAINER}" ]]; then
    docker exec -i "${PG_CONTAINER}" psql -U "${PG_USER}" "$@"
  else
    PGHOST="${PG_HOST}" PGPORT="${PG_PORT}" psql -U "${PG_USER}" "$@"
  fi
}

_pg_isready() {
  if [[ -n "${PG_CONTAINER}" ]]; then
    docker exec "${PG_CONTAINER}" pg_isready -U "${PG_USER}" >/dev/null 2>&1
  else
    PGHOST="${PG_HOST}" PGPORT="${PG_PORT}" pg_isready -U "${PG_USER}" >/dev/null 2>&1
  fi
}

# ── サマリ ──────────────────────────────────────────────────────
log "=============================================="
log "Restore test (dry-run / temporary DB)"
log "=============================================="
log "backup file       : ${BACKUP_FILE}"
log "backup size       : $(( BACKUP_SIZE / 1024 )) KB"
log "backup format     : ${BACKUP_FORMAT}"
log "env label         : ${ENV_TARGET}  (display only; no connection to real DB)"
log "temp DB name      : ${TEMP_DB_NAME}"
log "keep temp DB      : $([[ ${KEEP_TEMP_DB} -eq 1 ]] && echo yes || echo no)"
log "pg target         : $([[ -n "${PG_CONTAINER}" ]] && echo "container=${PG_CONTAINER}" || echo "host=${PG_HOST}:${PG_PORT}")"
log "pg user           : ${PG_USER}"
log "=============================================="

# ── pg_isready 接続確認 ─────────────────────────────────────────
if ! _pg_isready; then
  err "PostgreSQL is not reachable."
  err "  - host mode:   ensure PostgreSQL is running on ${PG_HOST}:${PG_PORT}"
  err "  - docker mode: ensure RESTORE_TEST_PG_CONTAINER is running"
  exit 2
fi
log "pg_isready: OK"

# ── 一時 DB 作成 ────────────────────────────────────────────────
log "Creating temporary DB: ${TEMP_DB_NAME}"
if ! _psql -d postgres -c "CREATE DATABASE \"${TEMP_DB_NAME}\";" >/dev/null 2>&1; then
  err "Failed to create temporary DB: ${TEMP_DB_NAME}"
  err "(database may already exist, or user '${PG_USER}' lacks CREATEDB privilege)"
  exit 2
fi
log "Temporary DB created."

# ── クリーンアップトラップ ─────────────────────────────────────
RESTORE_RC=1
INTEGRITY_RC=1
# shellcheck disable=SC2317  # invoked via `trap cleanup EXIT`
cleanup() {
  local exit_code=$?
  if [[ "${KEEP_TEMP_DB}" -eq 1 ]]; then
    log "--keep-temp-db: leaving ${TEMP_DB_NAME} for inspection."
    log "Drop manually: psql -U ${PG_USER} -d postgres -c 'DROP DATABASE \"${TEMP_DB_NAME}\";'"
  else
    # 安全装置: TEMP_DB_NAME が restore_test_ プレフィックスでない場合は DROP しない (paranoid)
    if [[ "${TEMP_DB_NAME}" == ${TEMP_DB_PREFIX}* ]]; then
      log "Dropping temporary DB: ${TEMP_DB_NAME}"
      _psql -d postgres -c "DROP DATABASE IF EXISTS \"${TEMP_DB_NAME}\";" >/dev/null 2>&1 || \
        warn "Failed to drop ${TEMP_DB_NAME}. Manual cleanup may be needed."
    else
      warn "Refusing to drop DB without '${TEMP_DB_PREFIX}' prefix: ${TEMP_DB_NAME}"
    fi
  fi
  exit "${exit_code}"
}
trap cleanup EXIT

# ── restore 実行 ────────────────────────────────────────────────
log "Restoring backup into ${TEMP_DB_NAME}..."
RESTORE_LOG="$(mktemp -t restore_test.XXXXXX.log)"

case "${BACKUP_FORMAT}" in
  sql.gz)
    if [[ -n "${PG_CONTAINER}" ]]; then
      if gunzip -c "${BACKUP_FILE}" \
          | docker exec -i "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TEMP_DB_NAME}" \
              -v ON_ERROR_STOP=1 \
          > "${RESTORE_LOG}" 2>&1; then
        RESTORE_RC=0
      fi
    else
      if PGHOST="${PG_HOST}" PGPORT="${PG_PORT}" \
          gunzip -c "${BACKUP_FILE}" \
          | psql -U "${PG_USER}" -d "${TEMP_DB_NAME}" -v ON_ERROR_STOP=1 \
          > "${RESTORE_LOG}" 2>&1; then
        RESTORE_RC=0
      fi
    fi
    ;;
  sql)
    if [[ -n "${PG_CONTAINER}" ]]; then
      if docker exec -i "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TEMP_DB_NAME}" \
            -v ON_ERROR_STOP=1 < "${BACKUP_FILE}" \
          > "${RESTORE_LOG}" 2>&1; then
        RESTORE_RC=0
      fi
    else
      if PGHOST="${PG_HOST}" PGPORT="${PG_PORT}" \
          psql -U "${PG_USER}" -d "${TEMP_DB_NAME}" -v ON_ERROR_STOP=1 < "${BACKUP_FILE}" \
          > "${RESTORE_LOG}" 2>&1; then
        RESTORE_RC=0
      fi
    fi
    ;;
  custom)
    # pg_restore は対象 DB を引数で指定する
    if [[ -n "${PG_CONTAINER}" ]]; then
      # コンテナ内に backup file を一旦コピーして使う
      TMP_IN_CONTAINER="/tmp/restore_test_$$.dump"
      if docker cp "${BACKUP_FILE}" "${PG_CONTAINER}:${TMP_IN_CONTAINER}" >/dev/null 2>&1 \
         && docker exec "${PG_CONTAINER}" \
              pg_restore -U "${PG_USER}" -d "${TEMP_DB_NAME}" --no-owner --no-acl \
                "${TMP_IN_CONTAINER}" \
              > "${RESTORE_LOG}" 2>&1; then
        RESTORE_RC=0
      fi
      docker exec "${PG_CONTAINER}" rm -f "${TMP_IN_CONTAINER}" 2>/dev/null || true
    else
      if PGHOST="${PG_HOST}" PGPORT="${PG_PORT}" \
          pg_restore -U "${PG_USER}" -d "${TEMP_DB_NAME}" --no-owner --no-acl \
            "${BACKUP_FILE}" \
          > "${RESTORE_LOG}" 2>&1; then
        RESTORE_RC=0
      fi
    fi
    ;;
esac

if [[ "${RESTORE_RC}" -ne 0 ]]; then
  err "Restore FAILED. Log tail:"
  tail -n 30 "${RESTORE_LOG}" >&2 || true
  log "Result: restore=NG"
  exit 1
fi
log "Restore: OK"

# ── 整合性確認 ──────────────────────────────────────────────────
log "Running integrity checks..."

# (a) テーブル数
TABLE_COUNT="$(_psql -d "${TEMP_DB_NAME}" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" \
  2>/dev/null | tr -d '[:space:]' || echo 0)"
log "  tables (public)      : ${TABLE_COUNT}"

# (b) 期待テーブルの存在確認
MISSING_TABLES=()
_missing_contains() {
  # POSIX-like helper to check whether a value is in MISSING_TABLES.
  local needle="$1"
  local item
  for item in "${MISSING_TABLES[@]}"; do
    [[ "${item}" == "${needle}" ]] && return 0
  done
  return 1
}
for t in "${EXPECTED_TABLES[@]}"; do
  exists="$(_psql -d "${TEMP_DB_NAME}" -tAc \
    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='${t}';" \
    2>/dev/null | tr -d '[:space:]' || echo "")"
  if [[ "${exists}" != "1" ]]; then
    MISSING_TABLES+=("${t}")
  fi
done

if [[ ${#MISSING_TABLES[@]} -gt 0 ]]; then
  warn "Missing expected tables: ${MISSING_TABLES[*]}"
else
  log "  expected tables      : all present (${#EXPECTED_TABLES[@]})"
fi

# (c) alembic_version head id
ALEMBIC_HEAD=""
if ! _missing_contains "alembic_version"; then
  ALEMBIC_HEAD="$(_psql -d "${TEMP_DB_NAME}" -tAc \
    "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null \
    | tr -d '[:space:]' || echo "")"
  if [[ -n "${ALEMBIC_HEAD}" ]]; then
    log "  alembic head         : ${ALEMBIC_HEAD}"
  else
    warn "alembic_version table exists but has no row."
  fi
else
  warn "alembic_version table not found in backup."
fi

# (d) 主要テーブル row count
log "  row counts:"
TOTAL_ROWS=0
for t in users ai_decisions proposals transactions portfolio_snapshots fund_allocations fee_transactions; do
  if _missing_contains "${t}"; then
    log "    ${t}: (missing)"
    continue
  fi
  cnt="$(_psql -d "${TEMP_DB_NAME}" -tAc "SELECT count(*) FROM \"${t}\";" 2>/dev/null \
    | tr -d '[:space:]' || echo 0)"
  log "    ${t}: ${cnt}"
  TOTAL_ROWS=$(( TOTAL_ROWS + ${cnt:-0} ))
done

# (e) FK 制約数
FK_COUNT="$(_psql -d "${TEMP_DB_NAME}" -tAc \
  "SELECT count(*) FROM information_schema.table_constraints
   WHERE constraint_schema='public' AND constraint_type='FOREIGN KEY';" \
  2>/dev/null | tr -d '[:space:]' || echo 0)"
log "  foreign key count    : ${FK_COUNT}"

# (f) FK 制約の妥当性チェック (referencing column が存在しているか)
INVALID_FK="$(_psql -d "${TEMP_DB_NAME}" -tAc \
  "SELECT count(*) FROM pg_constraint c
     JOIN pg_namespace n ON c.connamespace = n.oid
   WHERE n.nspname='public' AND c.contype='f' AND NOT c.convalidated;" \
  2>/dev/null | tr -d '[:space:]' || echo 0)"
log "  unvalidated FK count : ${INVALID_FK}"

# ── 判定 ────────────────────────────────────────────────────────
INTEGRITY_RC=0

# critical: tables が 0 件 → 復元失敗扱い
if [[ "${TABLE_COUNT}" -le 0 ]]; then
  err "No public tables found after restore."
  INTEGRITY_RC=1
fi

# critical: alembic_version が無い → 復元 NG (本プロジェクトは alembic 管理)
if [[ -z "${ALEMBIC_HEAD}" ]]; then
  err "alembic_version head not found. Restore is incomplete or backup is invalid."
  INTEGRITY_RC=1
fi

# critical: 期待テーブルのうち alembic_version, users が無い → NG
for t in users alembic_version; do
  if _missing_contains "${t}"; then
    err "Critical table missing: ${t}"
    INTEGRITY_RC=1
  fi
done

# critical: unvalidated FK が存在 → NG
if [[ "${INVALID_FK}" -gt 0 ]]; then
  err "Unvalidated FK constraints exist: ${INVALID_FK}"
  INTEGRITY_RC=1
fi

# ── 結果 ────────────────────────────────────────────────────────
log "=============================================="
log "Result summary"
log "=============================================="
log "  restore         : OK"
log "  tables          : ${TABLE_COUNT}"
log "  expected tables : $(( ${#EXPECTED_TABLES[@]} - ${#MISSING_TABLES[@]} )) / ${#EXPECTED_TABLES[@]}"
log "  alembic head    : ${ALEMBIC_HEAD:-<none>}"
log "  total rows      : ${TOTAL_ROWS}  (primary tables only)"
log "  FK count        : ${FK_COUNT}  (invalid: ${INVALID_FK})"
log "  integrity       : $([[ ${INTEGRITY_RC} -eq 0 ]] && echo OK || echo NG)"
log "=============================================="

if [[ "${INTEGRITY_RC}" -ne 0 ]]; then
  log "Final: NG"
  exit 1
fi

log "Final: OK"
exit 0
