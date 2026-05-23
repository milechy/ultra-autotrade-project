#!/usr/bin/env bash
# shellcheck shell=bash
#
# E2E test skeleton for emergency stop (staging only).
#
# Usage:
#   bash scripts/test_emergency_stop_e2e.sh [scenario_a|scenario_b|scenario_c|scenario_d|all]
#
# Environment (export before running):
#   STAGING_BACKEND_URL       e.g. https://staging.api.ultra-autotrade.example.com (TODO confirm)
#   STAGING_ADMIN_TOKEN       ADMIN role API token
#   STAGING_PARTNER_TOKEN     PARTNER role API token (for negative test in scenario C)
#   STAGING_DB_URL            psql connection string (postgres://...)
#   STAGING_BACKEND_CONTAINER docker container name of staging backend
#
# Notes:
#   - production 環境では実行しない (dev から prod SSH 不可)
#   - 本スクリプトは雛形であり、実 endpoint / HF 操作手段は TODO のまま
#   - scheduler フラグ取り違えに注意: staging=ON+shadow / prod=OFF
#
# Related:
#   docs/internal/emergency_stop_e2e_test_plan.md
#   docs/33_emergency_stop_governance.md

set -euo pipefail

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
SCENARIO="${1:-all}"

BACKEND_URL="${STAGING_BACKEND_URL:-}"
ADMIN_TOKEN="${STAGING_ADMIN_TOKEN:-}"
PARTNER_TOKEN="${STAGING_PARTNER_TOKEN:-}"
DB_URL="${STAGING_DB_URL:-}"
BACKEND_CONTAINER="${STAGING_BACKEND_CONTAINER:-staging-backend}"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_env() {
  local missing=0
  for var in "$@"; do
    if [[ -z "${!var:-}" ]]; then
      log "missing required env: $var"
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    die "set required env vars before running"
  fi
}

guard_not_prod() {
  # Refuse to run if the URL looks like production.
  if [[ "$BACKEND_URL" == *"api.ultra-autotrade.example.com"* ]] \
     && [[ "$BACKEND_URL" != *"staging"* ]]; then
    die "production URL detected; this script is staging only"
  fi
}

api_get() {
  local path="$1"
  curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${BACKEND_URL}${path}"
}

api_post_admin() {
  local path="$1"
  local body="${2:-{}}"
  curl -sS -X POST \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "${BACKEND_URL}${path}"
}

api_post_partner() {
  local path="$1"
  local body="${2:-{}}"
  curl -sS -X POST \
    -H "Authorization: Bearer ${PARTNER_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$body" \
    -w '\nHTTP_CODE:%{http_code}\n' \
    "${BACKEND_URL}${path}"
}

read_state_json() {
  docker exec "${BACKEND_CONTAINER}" cat /app/backend/state.json
}

# ------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------

# Scenario A: manual activation via API
scenario_a() {
  log "=== Scenario A: manual emergency stop ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN STAGING_BACKEND_CONTAINER

  log "Step 1: pre-state"
  api_get "/automation/status"

  log "Step 2: activate emergency stop"
  api_post_admin "/automation/emergency-stop" '{"reason":"e2e scenario A manual"}'

  log "Step 3: post-state"
  api_get "/automation/status"

  log "Step 4: state.json"
  read_state_json

  log "Step 5: process-news should return 503"
  curl -sS -X POST \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"text":"test news scenario A"}' \
    -w '\nHTTP_CODE:%{http_code}\n' \
    "${BACKEND_URL}/automation/process-news" || true

  log "Step 6: ai_decisions tail"
  if [[ -n "$DB_URL" ]]; then
    psql "$DB_URL" -c \
      "SELECT id, decision, created_at FROM ai_decisions ORDER BY created_at DESC LIMIT 5;"
  else
    log "STAGING_DB_URL not set; skipping psql"
  fi

  log "Scenario A done"
}

# Scenario B: automatic activation when HF < 1.6
scenario_b() {
  log "=== Scenario B: HF < 1.6 auto activation ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN STAGING_BACKEND_CONTAINER

  log "Step 1: pre-state"
  api_get "/aave/status"
  api_get "/automation/status"

  log "Step 2: lower HF (TODO: confirm method)"
  # TODO: pick one of
  #   - Aave testnet borrow を増やす
  #   - mock endpoint で record_health_factor(1.45)
  #   - staging 専用 admin endpoint
  log "PLACEHOLDER: HF lowering step not yet implemented"

  log "Step 3: wait for monitoring cycle"
  sleep 30

  log "Step 4: state.json"
  read_state_json

  log "Step 5: emergency log tail"
  docker logs "${BACKEND_CONTAINER}" 2>&1 | grep -i "emergency" | tail -20 || true

  log "Scenario B done"
}

# Scenario C: resume flow including PARTNER negative test and cooldown
scenario_c() {
  log "=== Scenario C: resume flow ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN STAGING_PARTNER_TOKEN STAGING_BACKEND_CONTAINER

  log "Step 1: HF recovery check"
  api_get "/aave/status"

  log "Step 2: PARTNER resume (expect 403)"
  api_post_partner "/automation/emergency-stop/resume" || true

  log "Step 3: ADMIN resume"
  api_post_admin "/automation/emergency-stop/resume"

  log "Step 4: post-state"
  api_get "/automation/status"

  log "Step 5: state.json"
  read_state_json

  log "Step 6: cooldown behaviour (TODO: spec)"
  log "PLACEHOLDER: cooldown verification not yet implemented"

  log "Step 7: process-news should succeed"
  curl -sS -X POST \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"text":"test news scenario C"}' \
    -w '\nHTTP_CODE:%{http_code}\n' \
    "${BACKEND_URL}/automation/process-news" || true

  log "Scenario C done"
}

# Scenario D: state.json persistence across restart
scenario_d() {
  log "=== Scenario D: state.json persistence ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN STAGING_BACKEND_CONTAINER

  log "Step 1: pre-restart state.json"
  read_state_json

  log "Step 2: restart container"
  docker restart "${BACKEND_CONTAINER}"

  log "Step 3: wait for health endpoint"
  local tries=0
  until curl -sf "${BACKEND_URL}/health" > /dev/null; do
    tries=$((tries + 1))
    if [[ "$tries" -gt 30 ]]; then
      die "backend did not come back within 60s"
    fi
    sleep 2
  done

  log "Step 4: post-restart state.json"
  read_state_json

  log "Step 5: automation status"
  api_get "/automation/status"

  log "Step 6: process-news should still 503"
  curl -sS -X POST \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"text":"test news scenario D"}' \
    -w '\nHTTP_CODE:%{http_code}\n' \
    "${BACKEND_URL}/automation/process-news" || true

  log "Step 7: restore log tail"
  docker logs "${BACKEND_CONTAINER}" 2>&1 \
    | grep -i "state.json\|emergency_stop" \
    | head -20 || true

  log "Scenario D done"
}

# ------------------------------------------------------------------
# Dispatch
# ------------------------------------------------------------------
main() {
  if [[ -n "$BACKEND_URL" ]]; then
    guard_not_prod
  fi

  case "$SCENARIO" in
    scenario_a) scenario_a ;;
    scenario_b) scenario_b ;;
    scenario_c) scenario_c ;;
    scenario_d) scenario_d ;;
    all)
      scenario_a
      scenario_c  # cleanup after A
      scenario_b
      scenario_d
      scenario_c  # final cleanup
      ;;
    *)
      die "unknown scenario: ${SCENARIO} (use scenario_a|scenario_b|scenario_c|scenario_d|all)"
      ;;
  esac
}

main "$@"
