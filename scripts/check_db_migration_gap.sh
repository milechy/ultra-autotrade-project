#!/bin/bash
# check_db_migration_gap.sh
#
# SQLAlchemy model vs actual DB schema gap detector.
# Detects columns/tables present in models but missing from DB.
# Outputs ALTER TABLE / CREATE TABLE statements for any gaps found.
#
# Usage:
#   ./scripts/check_db_migration_gap.sh                    # uses .env.production
#   ./scripts/check_db_migration_gap.sh --env staging      # uses .env.staging-new
#   DATABASE_URL=postgresql://... ./scripts/check_db_migration_gap.sh
#   BACKEND_CONTAINER=my-container ./scripts/check_db_migration_gap.sh
#
# Exit codes:
#   0 -- no schema gaps
#   1 -- gaps found (ALTER TABLE needed before deploying)
#   2 -- config error / DB unreachable (warning only, deploy continues)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DETECT_SCRIPT="${PROJECT_ROOT}/backend/scripts/detect_db_gaps.py"

# ── arg parse ───────────────────────────────────────────────────────────────
ENV_TARGET="${ENV_TARGET:-production}"
for arg in "$@"; do
  case "${arg}" in
    --env=*) ENV_TARGET="${arg#--env=}" ;;
    --env)   shift; ENV_TARGET="${1:-production}" ;;
    --help)  grep '^#' "$0" | head -30 | sed 's/^# \{0,1\}//'; exit 0 ;;
  esac
done

# ── resolve DATABASE_URL ────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ "${ENV_TARGET}" == "staging" ]]; then
    ENV_FILE="${PROJECT_ROOT}/.env.staging-new"
  else
    ENV_FILE="${PROJECT_ROOT}/.env.production"
  fi

  if [[ -f "${ENV_FILE}" ]]; then
    DATABASE_URL=$(grep -E '^DATABASE_URL=' "${ENV_FILE}" | head -1 | cut -d= -f2-)
    export DATABASE_URL
  fi
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[db-gap] ERROR: DATABASE_URL not set (${ENV_FILE:-<env file>} not found)"
  exit 2
fi

echo "[db-gap] env=${ENV_TARGET}"

# ── resolve compose network ─────────────────────────────────────────────────
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-ultra-autotrade-project}"
COMPOSE_NETWORK="${COMPOSE_PROJECT}_default"

# ── execution mode selection ────────────────────────────────────────────────
# Mode 1: docker run (preferred)
#   Mounts new code from host into an existing backend image that has sqlalchemy.
#   Compares NEW model definitions against the existing DB.
_try_docker_run() {
  local img
  img=$(docker images --format "{{.Repository}}:{{.Tag}}" 2>/dev/null \
    | grep -E "(backend[-_]blue|backend[-_]green|ultra-autotrade.*backend)" \
    | grep -v "<none>" \
    | head -1 || true)

  [[ -z "${img}" ]] && return 1

  local net="${COMPOSE_NETWORK}"
  if ! docker network inspect "${net}" >/dev/null 2>&1; then
    # Try alternate compose network names
    net=$(docker network ls --format "{{.Name}}" \
      | grep -E "ultra-autotrade" | head -1 || true)
    [[ -z "${net}" ]] && return 1
  fi

  echo "[db-gap] Mode: docker run (image=${img}, network=${net})"
  docker run --rm \
    --network "${net}" \
    -e DATABASE_URL="${DATABASE_URL}" \
    -v "${PROJECT_ROOT}/backend:/app:ro" \
    "${img}" \
    python3 /app/scripts/detect_db_gaps.py
}

# Mode 2: docker exec into running backend container
_try_docker_exec() {
  local cname
  for cname in \
    "${BACKEND_CONTAINER:-__unset__}" \
    ultra-autotrade-backend-blue-production \
    ultra-autotrade-backend-green-production \
    ultra-autotrade-backend-blue-staging-new \
    ultra-autotrade-backend-green-staging-new; do
    [[ "${cname}" == "__unset__" ]] && continue
    if docker ps --filter "name=^${cname}$" --filter "status=running" \
         --format "{{.Names}}" 2>/dev/null | grep -q "^${cname}$"; then
      echo "[db-gap] Mode: docker exec (container=${cname})"
      docker exec -i "${cname}" \
        env DATABASE_URL="${DATABASE_URL}" \
        python3 - < "${DETECT_SCRIPT}"
      return $?
    fi
  done
  return 1
}

# Mode 3: local python3 (fallback)
_try_local_python() {
  command -v python3 >/dev/null 2>&1 || return 1
  echo "[db-gap] Mode: local python3"
  cd "${PROJECT_ROOT}/backend"
  python3 "${DETECT_SCRIPT}"
}

# ── run ─────────────────────────────────────────────────────────────────────
if _try_docker_run; then
  exit $?
elif _try_docker_exec; then
  exit $?
elif _try_local_python; then
  exit $?
else
  echo "[db-gap] ERROR: No execution method available (need docker or python3)"
  exit 2
fi
