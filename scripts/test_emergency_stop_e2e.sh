#!/usr/bin/env bash
# shellcheck shell=bash
#
# E2E test script for emergency stop (staging only).
#
# Usage:
#   bash scripts/test_emergency_stop_e2e.sh [scenario_a|scenario_b|scenario_c|scenario_d|all]
#
# Environment (export before running):
#   STAGING_BACKEND_URL       e.g. https://api-staging.ultra-auto-trade.com
#                              (default fallback to internal nginx http://127.0.0.1:8082)
#   STAGING_ADMIN_TOKEN       ADMIN role Bearer token
#   STAGING_PARTNER_TOKEN     PARTNER role Bearer token (for negative test in scenario C)
#   STAGING_INTERNAL_TOKEN    INTERNAL_API_TOKEN value (for /automation/process-news)
#   STAGING_COMPOSE_FILE      docker-compose file (default: docker-compose.staging.yml)
#   STAGING_BACKEND_SERVICE   compose service name of active backend (default: backend-blue)
#   STAGING_DB_SERVICE        compose service name of postgres (default: postgres)
#   STAGING_DB_USER           postgres user (default: ultra)
#   STAGING_DB_NAME           postgres db (default: ultra_autotrade_staging)
#   COOLDOWN_SECONDS          cooldown wait between activate -> resume probes (default: 30)
#   MONITORING_INTERVAL_SECONDS  HF monitoring loop interval (default: 60, source: backend/app/automation/background_tasks.py)
#
# Notes:
#   - production 環境では実行しない (dev から prod SSH 不可)
#   - 実 endpoint:
#       * POST /api/automation/emergency-stop         (Bearer, PARTNER+)        [require_partner]
#       * POST /api/automation/emergency-stop/resume  (Bearer, ADMIN)            [require_admin]
#       * GET  /api/automation/status                                            [require_viewer]
#       * GET  /api/aave/status
#       * POST /automation/process-news               (X-Internal-Token)         [verify_internal_token]
#   - state.json は /var/run/ultra/state.json (volume: ultra-state-staging-new)
#   - scheduler フラグ取り違えに注意: staging=ON+shadow / prod=OFF
#   - process-news は emergency_stop=true の時 HTTP 200 を返すが
#     octobot_skipped_count == fetched_count となる (workflow rule_engine が HOLD する仕様)
#
# Related:
#   docs/internal/emergency_stop_e2e_test_plan.md
#   docs/33_emergency_stop_governance.md
#   backend/app/automation/automation_router.py
#   backend/app/api/automation_dashboard.py
#   backend/app/automation/monitoring_service.py
#   backend/app/aave/state_manager.py

set -euo pipefail

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
SCENARIO="${1:-all}"

BACKEND_URL="${STAGING_BACKEND_URL:-https://api-staging.ultra-auto-trade.com}"
ADMIN_TOKEN="${STAGING_ADMIN_TOKEN:-}"
PARTNER_TOKEN="${STAGING_PARTNER_TOKEN:-}"
INTERNAL_TOKEN="${STAGING_INTERNAL_TOKEN:-}"
COMPOSE_FILE="${STAGING_COMPOSE_FILE:-docker-compose.staging.yml}"
BACKEND_SERVICE="${STAGING_BACKEND_SERVICE:-backend-blue}"
DB_SERVICE="${STAGING_DB_SERVICE:-postgres}"
DB_USER="${STAGING_DB_USER:-ultra}"
DB_NAME="${STAGING_DB_NAME:-ultra_autotrade_staging}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-30}"
MONITORING_INTERVAL_SECONDS="${MONITORING_INTERVAL_SECONDS:-60}"

# Path of state.json inside backend container (matches AAVE_STATE_FILE_PATH default).
STATE_JSON_PATH="/var/run/ultra/state.json"

# Temporary working directory for response bodies (auto-cleanup on exit).
TMP_DIR="$(mktemp -d -t emerstop-e2e.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

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
  local var
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
  # Refuse to run if the URL looks like production (not staging).
  case "$BACKEND_URL" in
    *staging*) ;;
    *127.0.0.1*|*localhost*) ;;
    *)
      die "non-staging URL detected: $BACKEND_URL — this script is staging only"
      ;;
  esac
}

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

dc_exec_backend() {
  compose exec -T "$BACKEND_SERVICE" "$@"
}

dc_exec_db() {
  # psql in compose-managed postgres container.
  compose exec -T -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "$DB_SERVICE" \
    psql -U "$DB_USER" -d "$DB_NAME" "$@"
}

# curl wrappers — write body to $1, return HTTP code on stdout.
api_get_admin() {
  local path="$1"
  local out="$2"
  curl -sS -o "$out" -w '%{http_code}' \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${BACKEND_URL}${path}"
}

api_post_admin() {
  local path="$1"
  local body="${2:-{\}}"
  local out="$3"
  curl -sS -o "$out" -w '%{http_code}' -X POST \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "${BACKEND_URL}${path}"
}

api_post_partner() {
  local path="$1"
  local body="${2:-{\}}"
  local out="$3"
  curl -sS -o "$out" -w '%{http_code}' -X POST \
    -H "Authorization: Bearer ${PARTNER_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "${BACKEND_URL}${path}"
}

api_post_internal() {
  local path="$1"
  local body="${2:-{\}}"
  local out="$3"
  curl -sS -o "$out" -w '%{http_code}' -X POST \
    -H "X-Internal-Token: ${INTERNAL_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "${BACKEND_URL}${path}"
}

read_state_json() {
  dc_exec_backend cat "$STATE_JSON_PATH"
}

assert_jq_eq() {
  # assert_jq_eq <file> <jq-expr> <expected> <label>
  local file="$1" expr="$2" expected="$3" label="$4"
  local actual
  actual="$(jq -r "$expr" "$file")"
  if [[ "$actual" != "$expected" ]]; then
    log "FAIL: $label — expected '$expected', got '$actual'"
    log "--- response body ---"
    cat "$file" || true
    log "--- end body ---"
    die "assertion failed: $label"
  fi
  log "OK: $label = $actual"
}

assert_http_code() {
  # assert_http_code <actual> <expected> <label>
  local actual="$1" expected="$2" label="$3"
  if [[ "$actual" != "$expected" ]]; then
    die "FAIL: $label — expected HTTP $expected, got $actual"
  fi
  log "OK: $label HTTP $actual"
}

# ------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------

# Scenario A: manual activation via API (ADMIN).
scenario_a() {
  log "=== Scenario A: manual emergency stop (ADMIN) ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN

  local resp="$TMP_DIR/resp.json"
  local code

  log "Step 1: pre-state — GET /api/automation/status"
  code="$(api_get_admin "/api/automation/status" "$resp")"
  assert_http_code "$code" "200" "pre-status"
  assert_jq_eq "$resp" '.is_trading_paused' "false" "pre is_trading_paused=false"

  log "Step 2: POST /api/automation/emergency-stop"
  code="$(api_post_admin "/api/automation/emergency-stop" \
    '{"reason":"e2e scenario A manual"}' "$resp")"
  assert_http_code "$code" "200" "emergency-stop activate"
  assert_jq_eq "$resp" '.status' "stopped" "activate response status"

  log "Step 3: post-state — GET /api/automation/status"
  code="$(api_get_admin "/api/automation/status" "$resp")"
  assert_http_code "$code" "200" "post-status"
  assert_jq_eq "$resp" '.is_trading_paused' "true" "post is_trading_paused=true"

  log "Step 4: state.json snapshot"
  read_state_json | tee "$TMP_DIR/state.json"
  assert_jq_eq "$TMP_DIR/state.json" '.emergency_stop' "true" "state.json emergency_stop=true"
  assert_jq_eq "$TMP_DIR/state.json" '.mode' "hard_stop" "state.json mode=hard_stop"

  log "Step 5: process-news should NOT trade (octobot_skipped_count == fetched_count)"
  if [[ -n "$INTERNAL_TOKEN" ]]; then
    code="$(api_post_internal \
      "/automation/process-news?dry_run=true" \
      '{}' "$resp")"
    log "process-news HTTP $code"
    cat "$resp" || true
    # process-news は 200 を返すが、emergency_stop=true の時は workflow.py の
    # rule_engine_pre_check が "emergency_stop" 判定で全件 HOLD する。
    if [[ "$code" == "200" ]]; then
      local fetched skipped
      fetched="$(jq -r '.fetched_count' "$resp")"
      skipped="$(jq -r '.octobot_skipped_count' "$resp")"
      log "fetched=$fetched, skipped=$skipped"
      if [[ "$fetched" -gt 0 ]] && [[ "$skipped" != "$fetched" ]]; then
        die "FAIL: emergency_stop active but trades not all skipped (fetched=$fetched skipped=$skipped)"
      fi
      log "OK: workflow correctly skipped/held all pending items"
    fi
  else
    log "STAGING_INTERNAL_TOKEN not set; skipping process-news probe"
  fi

  log "Step 6: ai_decisions tail (psql)"
  dc_exec_db -c \
    "SELECT id, action, confidence, primary_provider, created_at FROM ai_decisions ORDER BY created_at DESC LIMIT 5;" \
    || log "WARN: psql query failed (DB unreachable?)"

  log "Step 7: emergency activation log tail"
  compose logs --tail=80 "$BACKEND_SERVICE" 2>&1 \
    | grep -iE "emergency_stop|HF_BELOW_EMERGENCY|activate_emergency_stop" \
    | tail -10 || true

  log "Scenario A done"
}

# Scenario B: automatic activation when HF < 1.6.
# staging で実 Aave の HF を意図的に下げるのは非現実的なので、2 経路を試す。
#
#   B-1: state.json を手動で書き換え → 起動時 _restore_emergency_state でフラグ復元
#   B-2: API モック呼出 (まだ未実装) — 案として記載のみ、実装時は staging admin endpoint を追加。
scenario_b() {
  log "=== Scenario B: HF < 1.6 auto activation (state.json 手動書き換え経路) ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN

  local resp="$TMP_DIR/resp.json"
  local code

  log "Step 1: pre-state"
  code="$(api_get_admin "/api/aave/status" "$resp")"
  log "GET /api/aave/status HTTP $code"
  cat "$resp" || true
  code="$(api_get_admin "/api/automation/status" "$resp")"
  assert_http_code "$code" "200" "automation/status"

  log "Step 2 (B-1): backup current state.json, then overwrite with HF=1.45"
  read_state_json > "$TMP_DIR/state.before.json"
  log "--- state.before.json ---"; cat "$TMP_DIR/state.before.json"; log "---"
  # Build the new state JSON (preserve unrelated fields, override emergency_stop / mode / HF / reason).
  jq '
    .emergency_stop = true
    | .mode = "hard_stop"
    | .health_factor = "1.45"
    | .reason = "e2e scenario B: HF 1.45 below emergency threshold 1.6 (synthetic)"
    | .last_update = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))
  ' "$TMP_DIR/state.before.json" > "$TMP_DIR/state.after.json"

  # Write atomically inside the backend container.
  dc_exec_backend sh -c "cat > ${STATE_JSON_PATH}.new && mv ${STATE_JSON_PATH}.new ${STATE_JSON_PATH}" \
    < "$TMP_DIR/state.after.json"

  log "Step 3: restart backend so monitoring_service._restore_emergency_state() picks it up"
  compose restart "$BACKEND_SERVICE"

  log "Step 4: wait for /api/automation/status to come back"
  local tries=0
  until code="$(api_get_admin "/api/automation/status" "$resp")" && [[ "$code" == "200" ]]; do
    tries=$((tries + 1))
    if [[ "$tries" -gt 30 ]]; then
      die "backend did not come back within 60s"
    fi
    sleep 2
  done

  log "Step 5: assert state restored"
  assert_jq_eq "$resp" '.is_trading_paused' "true" "after-restart is_trading_paused=true"
  read_state_json | tee "$TMP_DIR/state.after_restart.json"
  assert_jq_eq "$TMP_DIR/state.after_restart.json" '.emergency_stop' "true" "state.json emergency_stop=true persisted"

  log "Step 6: emergency restore log tail (expect 'Restored emergency_stop=True from state.json')"
  compose logs --tail=120 "$BACKEND_SERVICE" 2>&1 \
    | grep -iE "Restored emergency_stop|emergency|state.json" \
    | tail -15 || true

  log "Step 7 (B-2 NOTE): API mock route for record_health_factor() is not exposed."
  log "  To exercise the live monitoring loop, add a staging-only admin endpoint that calls"
  log "  monitoring_service.record_health_factor(Decimal('1.45')) and re-run this scenario."
  log "  Monitoring loop interval = ${MONITORING_INTERVAL_SECONDS}s (backend/app/automation/background_tasks.py)"

  log "Scenario B done (B-1 path only; B-2 requires future endpoint)"
}

# Scenario C: resume flow including PARTNER negative test and cooldown.
scenario_c() {
  log "=== Scenario C: resume flow (PARTNER 403 + ADMIN resume + cooldown) ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN STAGING_PARTNER_TOKEN

  local resp="$TMP_DIR/resp.json"
  local code

  log "Step 1: HF recovery check"
  code="$(api_get_admin "/api/aave/status" "$resp")"
  log "GET /api/aave/status HTTP $code"
  cat "$resp" || true

  log "Step 2: PARTNER resume (expect 403)"
  code="$(api_post_partner "/api/automation/emergency-stop/resume" '{}' "$resp")"
  assert_http_code "$code" "403" "PARTNER resume should be forbidden"

  log "Step 3: ADMIN resume"
  code="$(api_post_admin "/api/automation/emergency-stop/resume" '{}' "$resp")"
  assert_http_code "$code" "200" "ADMIN resume"
  assert_jq_eq "$resp" '.status' "resumed" "resume response status"

  log "Step 4: post-state"
  code="$(api_get_admin "/api/automation/status" "$resp")"
  assert_http_code "$code" "200" "post-resume status"
  assert_jq_eq "$resp" '.is_trading_paused' "false" "after-resume is_trading_paused=false"

  log "Step 5: state.json after resume"
  read_state_json | tee "$TMP_DIR/state.resumed.json"
  assert_jq_eq "$TMP_DIR/state.resumed.json" '.emergency_stop' "false" "state.json emergency_stop=false"

  log "Step 6: cooldown behaviour"
  log "  NOTE: there is no dedicated 'emergency_stop cooldown'. The closest spec is:"
  log "    - HF < ${MONITORING_INTERVAL_SECONDS}s で再評価 → 危険域なら HARD_STOP に戻る (monitoring_service.record_health_factor)"
  log "    - AAVE_TRADE_COOLDOWN_SECONDS は trade 間隔の throttle, emergency と直交"
  log "  → resume 後 COOLDOWN_SECONDS=${COOLDOWN_SECONDS}s 待って二重トリガー無しを確認"
  sleep "$COOLDOWN_SECONDS"
  code="$(api_get_admin "/api/automation/status" "$resp")"
  assert_jq_eq "$resp" '.is_trading_paused' "false" "cooldown still resumed (HF should be healthy)"

  log "Step 7: process-news should succeed (no rule_engine block)"
  if [[ -n "$INTERNAL_TOKEN" ]]; then
    code="$(api_post_internal \
      "/automation/process-news?dry_run=true" \
      '{}' "$resp")"
    log "process-news HTTP $code"
    cat "$resp" || true
    assert_http_code "$code" "200" "process-news after resume"
  else
    log "STAGING_INTERNAL_TOKEN not set; skipping process-news probe"
  fi

  log "Scenario C done"
}

# Scenario D: state.json persistence across restart.
scenario_d() {
  log "=== Scenario D: state.json persistence across restart ==="
  require_env STAGING_BACKEND_URL STAGING_ADMIN_TOKEN

  local resp="$TMP_DIR/resp.json"
  local code

  log "Step 0: activate emergency stop (precondition)"
  code="$(api_post_admin "/api/automation/emergency-stop" \
    '{"reason":"e2e scenario D precondition"}' "$resp")"
  assert_http_code "$code" "200" "pre-restart activate"

  log "Step 1: pre-restart state.json"
  read_state_json | tee "$TMP_DIR/state.pre_restart.json"
  assert_jq_eq "$TMP_DIR/state.pre_restart.json" '.emergency_stop' "true" "pre-restart emergency_stop=true"

  log "Step 2: docker compose restart $BACKEND_SERVICE"
  compose restart "$BACKEND_SERVICE"

  log "Step 3: wait for /api/automation/status (max 60s)"
  local tries=0
  until code="$(api_get_admin "/api/automation/status" "$resp")" && [[ "$code" == "200" ]]; do
    tries=$((tries + 1))
    if [[ "$tries" -gt 30 ]]; then
      die "backend did not come back within 60s"
    fi
    sleep 2
  done

  log "Step 4: post-restart state.json"
  read_state_json | tee "$TMP_DIR/state.post_restart.json"
  assert_jq_eq "$TMP_DIR/state.post_restart.json" '.emergency_stop' "true" "post-restart emergency_stop=true persisted"

  log "Step 5: automation status"
  assert_jq_eq "$resp" '.is_trading_paused' "true" "post-restart is_trading_paused=true"

  log "Step 6: process-news should still be blocked (skipped == fetched)"
  if [[ -n "$INTERNAL_TOKEN" ]]; then
    code="$(api_post_internal \
      "/automation/process-news?dry_run=true" \
      '{}' "$resp")"
    log "process-news HTTP $code"
    cat "$resp" || true
    if [[ "$code" == "200" ]]; then
      local fetched skipped
      fetched="$(jq -r '.fetched_count' "$resp")"
      skipped="$(jq -r '.octobot_skipped_count' "$resp")"
      if [[ "$fetched" -gt 0 ]] && [[ "$skipped" != "$fetched" ]]; then
        die "FAIL: post-restart trades not all skipped"
      fi
    fi
  else
    log "STAGING_INTERNAL_TOKEN not set; skipping process-news probe"
  fi

  log "Step 7: restore log tail (expect 'Restored emergency_stop=True from state.json')"
  compose logs --tail=120 "$BACKEND_SERVICE" 2>&1 \
    | grep -iE "Restored emergency_stop|state.json|emergency_stop" \
    | tail -20 || true

  log "Scenario D done — cleanup with scenario_c"
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
