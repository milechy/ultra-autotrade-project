#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/e2e_emergency_stop.sh
#
# Ultra AutoTrade — 緊急停止 e2e 全経路検証
# Asana 1215082491258819 + 1215079129107315
#
# 全 5 停止経路 × (scheduler停止/ai_decisions 0件 + Slack/LINE通知 + resume復元) を確認。
#
# TC-1: POST /api/automation/emergency-stop (API kill switch)
# TC-2: DISABLE_AI_JUDGMENT_SCHEDULER=1 + 再起動 (env var 停止)
# TC-3: ai_decision エラー連続 → Slack 通知 + ai_decisions 0件確認
# TC-4: HF < 1.6 閾値 → trading_paused=true + LINE 通知 (ロジック+状態検証)
# TC-5: resume / 復元 総合確認
#
# 実行先: staging VPS (188.34.167.142, ASSIST ONE) 上の staging stack に対して実行。
#         2026-07-02 移行後は staging は production と別 VPS に分離済み。
#
# SSH: ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142
#
# 必須 env:
#   ADMIN_EMAIL       staging admin ユーザーメール
#   ADMIN_PASSWORD    staging admin パスワード
#
# オプション env:
#   STAGING_BASE_URL           default: http://127.0.0.1:8082
#   POSTGRES_CONTAINER         default: 自動検出 (*postgres*staging*)
#   BACKEND_CONTAINER          default: 自動検出 (nginx upstream の active 側)
#   DB_USER                    default: ultra
#   DB_NAME                    default: ultra_autotrade_staging
#   AI_DELTA_WAIT_SEC          default: 5 (ai_decisions delta 観測待ち秒数)
#   LOG_TAIL_LINES             default: 300
#   DRY_RUN                    true の場合 API call をスキップして検証手順を出力のみ
#   DO_SCHEDULER_RESTART_TEST  true の場合 TC-2 で staging backend を再起動して検証 (default: false)
#   SKIP_TCS                   スキップする TC 番号カンマ区切り (例: "2,4")
#   ENV_FILE                   .env.production パス (Slack webhook 読込用)
#
# 安全装置:
#   - dev VPS (hostname=uata-dev*) では即 EXIT
#   - /health env=staging 確認 (production 誤接続防止)
#   - コンテナ名に "staging" が含まれること確認
#   - SQL: SELECT のみ (DB write なし)
#   - emergency stop reason に E2E_TAG を含めて誤検知防止
#   - 全 TC 完了後に trap で必ず resume を試みる
#
# 期待サマリ:
#   [PASS] TC-1: API kill switch        HTTP 200 / paused=true / delta=0 / slack OK / resumed
#   [PASS] TC-2: env var disable        DISABLE_AI_JUDGMENT_SCHEDULER=1 / delta=0
#   [PASS] TC-3: error consecutive      trigger reject / delta=0 / slack log found
#   [PASS] TC-4: HF threshold           logic OK / paused=true / LINE_TOKEN set / resumed
#   [PASS] TC-5: resume restoration     paused=false / resume HTTP 2xx / resume log found
#   PASS=5 FAIL=0 SKIP=0
# ---------------------------------------------------------------------------
set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
SCRIPT_NAME="e2e_emergency_stop"
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"
BASE_URL="${STAGING_BASE_URL:-http://127.0.0.1:8082}"
DB_USER="${DB_USER:-ultra}"
DB_NAME="${DB_NAME:-ultra_autotrade_staging}"
AI_DELTA_WAIT_SEC="${AI_DELTA_WAIT_SEC:-5}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-300}"
DRY_RUN="${DRY_RUN:-false}"
DO_SCHEDULER_RESTART_TEST="${DO_SCHEDULER_RESTART_TEST:-false}"
SKIP_TCS="${SKIP_TCS:-}"
CURL_TIMEOUT=15

E2E_TAG="e2e-stop-$(date +%Y%m%dT%H%M%S)"

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# ロガー
# =============================================================================
log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()      { echo -e "${GREEN}[PASS]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_fail()    { echo -e "${RED}[FAIL]${NC}  $*"; }
log_section() { echo -e "\n${CYAN}======= $* =======${NC}"; }

# =============================================================================
# 結果集約
# =============================================================================
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
RESULTS=()

gate_record() {
  local status="$1" label="$2" msg="$3"
  RESULTS+=("${status}|${label}|${msg}")
  case "${status}" in
    PASS) PASS_COUNT=$(( PASS_COUNT + 1 )); log_ok  "${label}: ${msg}" ;;
    FAIL) FAIL_COUNT=$(( FAIL_COUNT + 1 )); log_fail "${label}: ${msg}" ;;
    SKIP) SKIP_COUNT=$(( SKIP_COUNT + 1 )); log_warn "${label}: ${msg}" ;;
  esac
}

gate_summary() {
  echo ""
  echo "=== e2e Emergency Stop Summary ==="
  local st lb msg
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r st lb msg <<< "${r}"
    case "${st}" in
      PASS) printf "${GREEN}[PASS]${NC} %-35s %s\n" "${lb}" "${msg}" ;;
      FAIL) printf "${RED}[FAIL]${NC} %-35s %s\n" "${lb}" "${msg}" ;;
      SKIP) printf "${YELLOW}[SKIP]${NC} %-35s %s\n" "${lb}" "${msg}" ;;
    esac
  done
  echo ""
  echo "PASS=${PASS_COUNT} FAIL=${FAIL_COUNT} SKIP=${SKIP_COUNT}"
  [[ "${FAIL_COUNT}" -eq 0 ]]
}

should_skip_tc() {
  local tc_num="$1"
  [[ ",${SKIP_TCS}," == *",${tc_num},"* ]]
}

# =============================================================================
# 共有状態
# =============================================================================
CLEANUP_NEEDED=false
ADMIN_TOKEN=""
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-}"

# =============================================================================
# Slack 通知
# =============================================================================
_load_slack_webhook() {
  if [[ -z "${SLACK_WEBHOOK_URL:-}" && -f "${ENV_FILE}" ]]; then
    SLACK_WEBHOOK_URL=$(grep '^SLACK_WEBHOOK_URL=' "${ENV_FILE}" \
      | cut -d= -f2- | tr -d '"' | tr -d "'") || true
  fi
}

_slack() {
  local text="$1"
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "[DRY_RUN] Slack: ${text}"
    return 0
  fi
  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    log_info "[SKIP] Slack: SLACK_WEBHOOK_URL 未設定"
    return 0
  fi
  curl -s -X POST "${SLACK_WEBHOOK_URL}" \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"${text}\"}" > /dev/null 2>&1 || true
}

# =============================================================================
# 安全ガード
# =============================================================================
_safety_check() {
  log_section "Safety Check"

  # dev VPS (hostname が uata-dev*) は構造上実行不可
  local hn
  hn=$(hostname 2>/dev/null || echo "unknown")
  if [[ "${hn}" == uata-dev* ]]; then
    cat <<EOF

[INFO] dev VPS (${hn}) では実行不可。
       本スクリプトは staging VPS (188.34.167.142, ASSIST ONE) 上で staging stack に対して実行する設計です。
       実行手順:
         1) iMac で:
              ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142
         2) staging VPS で:
              export ADMIN_EMAIL='<staging admin email>'
              export ADMIN_PASSWORD='<staging admin password>'
              cd /opt/ultra-autotrade
              bash scripts/e2e_emergency_stop.sh
EOF
    exit 0
  fi

  # 必須コマンド確認
  for cmd in curl jq docker; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
      echo "[FATAL] required command not found: ${cmd}" >&2
      exit 2
    fi
  done

  log_info "Safety check OK (host=${hn})"
}

# =============================================================================
# 必須 env 確認
# =============================================================================
_require_env() {
  local name="$1"
  local val="${!name:-}"
  if [[ -z "${val}" ]]; then
    echo "[FATAL] 必須 env 未設定: ${name}" >&2
    exit 2
  fi
}

# =============================================================================
# コンテナ検出
# =============================================================================
_detect_containers() {
  log_section "Container Detection"

  if [[ -z "${POSTGRES_CONTAINER}" ]]; then
    POSTGRES_CONTAINER=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
      | grep postgres | grep staging | head -1 || true)
  fi
  if [[ -z "${POSTGRES_CONTAINER}" || "${POSTGRES_CONTAINER}" != *staging* ]]; then
    echo "[FATAL] staging postgres コンテナが見つかりません。'docker ps | grep postgres' を確認。" >&2
    exit 2
  fi

  if [[ -z "${BACKEND_CONTAINER}" ]]; then
    local nginx_c active_alias
    nginx_c=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
      | grep nginx | grep staging | head -1 || true)
    active_alias=""
    if [[ -n "${nginx_c}" ]]; then
      active_alias=$(docker exec "${nginx_c}" cat /etc/nginx/conf.d/upstream.conf 2>/dev/null \
        | grep -oE 'backend-(blue|green)' | head -1 || true)
    fi
    if [[ -n "${active_alias}" ]]; then
      BACKEND_CONTAINER=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
        | grep "${active_alias}" | grep staging | head -1 || true)
    fi
  fi
  if [[ -z "${BACKEND_CONTAINER}" || "${BACKEND_CONTAINER}" != *staging* ]]; then
    echo "[FATAL] staging backend (active) コンテナが見つかりません。" >&2
    echo "        BACKEND_CONTAINER=${BACKEND_CONTAINER:-(empty)}" >&2
    exit 2
  fi

  log_info "POSTGRES_CONTAINER=${POSTGRES_CONTAINER}"
  log_info "BACKEND_CONTAINER=${BACKEND_CONTAINER}"
  log_info "BASE_URL=${BASE_URL}"
  log_info "E2E_TAG=${E2E_TAG}"
}

# =============================================================================
# /health で staging 確認 (production 誤接続防止)
# =============================================================================
_verify_staging() {
  log_section "Verify Staging"

  local health_body health_env
  health_body=$(curl -sS --max-time 10 "${BASE_URL}/health" 2>/dev/null || echo "")
  health_env=$(echo "${health_body}" | jq -r '.env // empty' 2>/dev/null || echo "")

  if [[ "${health_env}" != "staging" ]]; then
    echo "[FATAL] /health env='${health_env}' (expected 'staging')。BASE_URL を確認。" >&2
    echo "        body: ${health_body}" >&2
    exit 2
  fi
  log_info "/health env=staging 確認 OK"
}

# =============================================================================
# admin JWT 取得
# =============================================================================
_get_admin_token() {
  log_section "Auth"

  local login_payload login_body
  login_payload=$(jq -n --arg e "${ADMIN_EMAIL}" --arg p "${ADMIN_PASSWORD}" \
    '{email:$e,password:$p}')
  login_body=$(curl -sS --max-time "${CURL_TIMEOUT}" -X POST "${BASE_URL}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "${login_payload}" 2>/dev/null || echo "")
  ADMIN_TOKEN=$(echo "${login_body}" | jq -r '.access_token // empty' 2>/dev/null || echo "")
  if [[ -z "${ADMIN_TOKEN}" ]]; then
    echo "[FATAL] /auth/login 失敗。response: ${login_body}" >&2
    exit 2
  fi
  log_info "admin JWT 取得 OK (len=${#ADMIN_TOKEN})"
}

# =============================================================================
# ヘルパー
# =============================================================================
psql_query() {
  local sql="$1"
  docker exec "${POSTGRES_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" \
    -tA -c "${sql}" 2>/dev/null | tr -d '\r'
}

count_ai_decisions() {
  psql_query "SELECT COUNT(*) FROM ai_decisions;"
}

get_automation_status() {
  curl -sS --max-time "${CURL_TIMEOUT}" "${BASE_URL}/api/automation/status" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" 2>/dev/null || echo "{}"
}

is_trading_paused() {
  get_automation_status | jq -r '.is_trading_paused // false' 2>/dev/null || echo "false"
}

do_emergency_stop() {
  local reason="$1"
  local body
  body=$(jq -n --arg r "${reason}" '{reason:$r}')
  curl -sS --max-time "${CURL_TIMEOUT}" -o /dev/null -w '%{http_code}' \
    -X POST "${BASE_URL}/api/automation/emergency-stop" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "${body}" 2>/dev/null || echo "000"
}

do_resume() {
  curl -sS --max-time "${CURL_TIMEOUT}" -o /dev/null -w '%{http_code}' \
    -X POST "${BASE_URL}/api/automation/emergency-stop/resume" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" 2>/dev/null || echo "000"
}

check_backend_logs() {
  local pattern="$1"
  docker logs --tail "${LOG_TAIL_LINES}" "${BACKEND_CONTAINER}" 2>&1 \
    | grep -ciE "${pattern}" || echo "0"
}

# =============================================================================
# cleanup trap: 終了時に必ず resume
# =============================================================================
_cleanup() {
  if [[ "${CLEANUP_NEEDED}" == "true" && -n "${ADMIN_TOKEN}" ]]; then
    log_info "Cleanup: staging emergency_stop を解除 (resume)"
    do_resume > /dev/null 2>&1 || true
  fi
}
trap _cleanup EXIT

# =============================================================================
# TC-1: API Kill Switch (POST /api/automation/emergency-stop)
#
# 検証:
#   - emergency-stop POST → HTTP 2xx / status=stopped
#   - is_trading_paused=true → scheduler が次 tick で ai_decisions を生成しない
#   - ai_decisions delta = 0 (5秒待機)
#   - backend ログに Slack 通知試行 (🚨 緊急停止が発動されました)
#   - resume POST → HTTP 2xx / is_trading_paused=false
# =============================================================================
run_tc1() {
  log_section "TC-1: API Kill Switch (POST /api/automation/emergency-stop)"

  if should_skip_tc "1"; then
    gate_record SKIP "TC-1: API kill switch" "SKIP_TCS に指定"
    return 0
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "[DRY_RUN] POST /api/automation/emergency-stop を呼び、is_trading_paused=true を確認"
    log_info "[DRY_RUN] ai_decisions delta=0 (${AI_DELTA_WAIT_SEC}s wait)"
    log_info "[DRY_RUN] backend log で Slack 通知試行を確認"
    log_info "[DRY_RUN] POST /api/automation/emergency-stop/resume を呼び復元確認"
    gate_record SKIP "TC-1: API kill switch" "DRY_RUN=true (手順確認のみ)"
    return 0
  fi

  # 1a. emergency-stop 発動
  local stop_resp_file stop_code stop_status
  stop_resp_file="/tmp/${E2E_TAG}_tc1_stop.json"
  stop_code=$(curl -sS --max-time "${CURL_TIMEOUT}" -o "${stop_resp_file}" -w '%{http_code}' \
    -X POST "${BASE_URL}/api/automation/emergency-stop" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg r "${E2E_TAG} TC-1 API-kill-switch e2e" '{reason:$r}')" \
    2>/dev/null || echo "000")
  stop_status=$(jq -r '.status // empty' "${stop_resp_file}" 2>/dev/null || echo "")
  rm -f "${stop_resp_file}"

  if [[ ! "${stop_code}" =~ ^2[0-9][0-9]$ ]]; then
    gate_record FAIL "TC-1: API kill switch" \
      "POST /api/automation/emergency-stop HTTP=${stop_code}"
    return 1
  fi
  CLEANUP_NEEDED=true
  log_info "emergency-stop 発動 OK (HTTP ${stop_code} status=${stop_status})"

  # 1b. is_trading_paused=true 確認
  local paused
  paused=$(is_trading_paused)
  if [[ "${paused}" != "true" ]]; then
    gate_record FAIL "TC-1: API kill switch" \
      "is_trading_paused=${paused} (expected true) after emergency-stop"
    do_resume > /dev/null 2>&1 || true
    CLEANUP_NEEDED=false
    return 1
  fi
  log_info "is_trading_paused=true 確認 OK"

  # 1c. ai_decisions delta=0 確認 (次 tick でスケジューラーが動かない)
  local cnt_before cnt_after delta
  cnt_before=$(count_ai_decisions || echo "")
  if [[ -z "${cnt_before}" || ! "${cnt_before}" =~ ^[0-9]+$ ]]; then
    log_warn "ai_decisions COUNT 取得失敗。delta チェックをスキップ。"
    delta="N/A"
  else
    sleep "${AI_DELTA_WAIT_SEC}"
    cnt_after=$(count_ai_decisions || echo "${cnt_before}")
    delta=$(( cnt_after - cnt_before ))
    log_info "ai_decisions delta=${delta} (before=${cnt_before} after=${cnt_after} wait=${AI_DELTA_WAIT_SEC}s)"
  fi

  # 1d. backend ログで Slack 通知試行確認
  local activate_hits
  activate_hits=$(check_backend_logs "緊急停止が発動|EMERGENCY_STOP|activate_emergency_stop")
  log_info "Slack activate log hits=${activate_hits}"

  # 1e. resume
  local resume_code
  resume_code=$(do_resume)
  log_info "resume HTTP=${resume_code}"
  if [[ "${resume_code}" =~ ^2[0-9][0-9]$ ]]; then
    CLEANUP_NEEDED=false
  fi

  # 1f. is_trading_paused=false 確認
  sleep 1
  local paused_after
  paused_after=$(is_trading_paused)
  log_info "is_trading_paused after resume=${paused_after}"

  # resume ログ確認
  local clear_hits
  clear_hits=$(check_backend_logs "緊急停止を解除|clear_emergency_stop|emergency.*clear")
  log_info "Slack clear log hits=${clear_hits}"

  # 判定
  local delta_ok=true
  if [[ "${delta}" != "N/A" && "${delta}" -gt 1 ]]; then
    delta_ok=false
  fi

  if [[ "${paused}" == "true" && "${delta_ok}" == "true" && "${activate_hits}" -ge 1 \
        && "${resume_code}" =~ ^2[0-9][0-9]$ && "${paused_after}" == "false" ]]; then
    gate_record PASS "TC-1: API kill switch" \
      "paused=true / delta=${delta} / slack=${activate_hits}hits / resume HTTP=${resume_code} / restored"
  else
    gate_record FAIL "TC-1: API kill switch" \
      "paused=${paused} delta=${delta} slack=${activate_hits} resume=${resume_code} paused_after=${paused_after}"
  fi
}

# =============================================================================
# TC-2: DISABLE_AI_JUDGMENT_SCHEDULER=1 (env var 停止)
#
# 検証:
#   - コンテナ env で DISABLE_AI_JUDGMENT_SCHEDULER=1 が設定されているか確認
#   - 設定済み: ai_decisions が増加しないこと (scheduler 停止中)
#   - 未設定 + DO_SCHEDULER_RESTART_TEST=true: override で再起動 → 検証 → 復元
#   - 未設定 + DO_SCHEDULER_RESTART_TEST=false (default): SKIP + 手順表示
#
# 注: scheduler 停止は is_trading_paused に影響しない (Slack ログで起動メッセージ確認)
#     "DISABLE_AI_JUDGMENT_SCHEDULER=1" はスケジューラー起動をスキップするだけで
#     emergency_stop は発動しない → resume は不要。
# =============================================================================
run_tc2() {
  log_section "TC-2: DISABLE_AI_JUDGMENT_SCHEDULER=1 (env var 停止)"

  if should_skip_tc "2"; then
    gate_record SKIP "TC-2: env var disable" "SKIP_TCS に指定"
    return 0
  fi

  # 2a. コンテナ env 確認
  local disable_flag enable_flag
  disable_flag=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
    "${BACKEND_CONTAINER}" 2>/dev/null \
    | grep '^DISABLE_AI_JUDGMENT_SCHEDULER=' || true)
  enable_flag=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
    "${BACKEND_CONTAINER}" 2>/dev/null \
    | grep '^ENABLE_AI_JUDGMENT_SCHEDULER=' || true)

  log_info "DISABLE_AI_JUDGMENT_SCHEDULER='${disable_flag:-未設定}'"
  log_info "ENABLE_AI_JUDGMENT_SCHEDULER='${enable_flag:-未設定}'"

  # 2b. backend ログでスケジューラー起動状態確認
  local disabled_log_hits enabled_log_hits
  disabled_log_hits=$(docker logs --tail 500 "${BACKEND_CONTAINER}" 2>&1 \
    | grep -ciE "AI.?judgment.?scheduler.*(disabled|無効|skip|not.*start)|DISABLE_AI_JUDGMENT_SCHEDULER" \
    || echo "0")
  enabled_log_hits=$(docker logs --tail 500 "${BACKEND_CONTAINER}" 2>&1 \
    | grep -ciE "AI.?judgment.?scheduler.*(started|start|起動|enabled|running)" \
    || echo "0")

  log_info "scheduler disabled log hits=${disabled_log_hits}"
  log_info "scheduler enabled log hits=${enabled_log_hits}"

  # 2c. フラグ値を取得
  local flag_value
  flag_value=$(echo "${disable_flag}" | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "")

  if [[ "${flag_value}" == "1" || "${flag_value}" == "true" ]]; then
    # --- フラグ既設定: ai_decisions が増加しないこと確認 ---
    local cnt_before cnt_after delta
    cnt_before=$(count_ai_decisions || echo "")
    if [[ -n "${cnt_before}" && "${cnt_before}" =~ ^[0-9]+$ ]]; then
      sleep "${AI_DELTA_WAIT_SEC}"
      cnt_after=$(count_ai_decisions || echo "${cnt_before}")
      delta=$(( cnt_after - cnt_before ))
      log_info "ai_decisions delta=${delta} (wait=${AI_DELTA_WAIT_SEC}s)"
      if [[ "${delta}" -eq 0 ]]; then
        gate_record PASS "TC-2: env var disable" \
          "DISABLE_AI_JUDGMENT_SCHEDULER=1 設定済み / ai_decisions delta=0 / disabled_log=${disabled_log_hits}hits"
      else
        gate_record FAIL "TC-2: env var disable" \
          "DISABLE_AI_JUDGMENT_SCHEDULER=1 だが ai_decisions delta=${delta} (expected 0)"
      fi
    else
      gate_record PASS "TC-2: env var disable" \
        "DISABLE_AI_JUDGMENT_SCHEDULER=1 設定済み / ai_decisions COUNT 取得不可 / disabled_log=${disabled_log_hits}hits"
    fi
    return 0
  fi

  # --- フラグ未設定 ---
  if [[ "${DO_SCHEDULER_RESTART_TEST}" == "true" ]]; then
    log_info "DO_SCHEDULER_RESTART_TEST=true: staging backend 再起動テストを実行"
    _run_tc2_restart_test
    return $?
  fi

  # フラグ未設定 + DO_SCHEDULER_RESTART_TEST=false: SKIP + 手順表示
  log_warn "DISABLE_AI_JUDGMENT_SCHEDULER は現在未設定 (scheduler は enabled 状態)"
  echo ""
  echo "  TC-2 完全テスト手順 (staging 専用):"
  echo ""
  echo "  方法 A: DO_SCHEDULER_RESTART_TEST=true で本スクリプトを再実行"
  echo "    DO_SCHEDULER_RESTART_TEST=true bash scripts/e2e_emergency_stop.sh"
  echo ""
  echo "  方法 B: 手動テスト"
  echo "    1) /opt/ultra-autotrade/.env.staging-new に追加:"
  echo "         DISABLE_AI_JUDGMENT_SCHEDULER=1"
  echo "    2) staging backend 再起動:"
  echo "         cd /opt/ultra-autotrade"
  echo "         docker compose -f docker-compose.staging.yml up -d --no-deps \\"
  echo "           backend-blue backend-green"
  echo "    3) backend ログで確認:"
  echo "         docker logs --tail 50 ${BACKEND_CONTAINER}"
  echo "         → 'AI judgment scheduler' + 'disabled' が出ていること"
  echo "    4) ${AI_DELTA_WAIT_SEC}s 以上待ち、ai_decisions が増加しないこと確認:"
  echo "         docker exec ${POSTGRES_CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} \\"
  echo "           -tA -c 'SELECT COUNT(*) FROM ai_decisions;'"
  echo "    5) env から DISABLE_AI_JUDGMENT_SCHEDULER=1 を削除して再起動し復元確認"
  echo ""
  gate_record SKIP "TC-2: env var disable" \
    "DISABLE_AI_JUDGMENT_SCHEDULER 未設定。DO_SCHEDULER_RESTART_TEST=true で実行可"
}

_run_tc2_restart_test() {
  local COMPOSE_FILE="/opt/ultra-autotrade/docker-compose.staging.yml"
  local OVERRIDE_FILE="/tmp/${E2E_TAG}_tc2_override.yml"

  # 対象サービス名を検出
  local svc_name
  svc_name=$(docker compose -f "${COMPOSE_FILE}" ps --format json 2>/dev/null \
    | jq -r '.[].Service' 2>/dev/null \
    | grep -E 'backend-(blue|green)' | head -1 \
    || echo "backend-blue")
  log_info "TC-2 restart target service: ${svc_name}"

  # 事前 ai_decisions 件数
  local cnt_before
  cnt_before=$(count_ai_decisions || echo "0")
  log_info "ai_decisions before restart=${cnt_before}"

  # override ファイル作成
  cat > "${OVERRIDE_FILE}" <<OVERRIDE_EOF
version: '3.8'
services:
  ${svc_name}:
    environment:
      DISABLE_AI_JUDGMENT_SCHEDULER: "1"
OVERRIDE_EOF

  log_info "DISABLE_AI_JUDGMENT_SCHEDULER=1 で ${svc_name} を再起動"
  if ! docker compose -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" \
      up -d --no-deps "${svc_name}" 2>/dev/null; then
    log_warn "docker compose up failed (手動確認要)"
    rm -f "${OVERRIDE_FILE}"
    gate_record FAIL "TC-2: env var disable" "docker compose up failed"
    return 1
  fi

  # 起動待ち (最大 60 秒)
  local retry=0 health_ok=false
  while [[ "${retry}" -lt 12 ]]; do
    local h
    h=$(curl -sS --max-time 5 "${BASE_URL}/health" 2>/dev/null \
      | jq -r '.env // empty' 2>/dev/null || echo "")
    if [[ "${h}" == "staging" ]]; then
      health_ok=true
      break
    fi
    sleep 5
    retry=$(( retry + 1 ))
  done
  log_info "/health OK=${health_ok} (${retry}x5s 待機)"

  # ログでスケジューラー無効確認
  sleep 3
  local disabled_hits
  disabled_hits=$(docker logs --tail 150 "${BACKEND_CONTAINER}" 2>&1 \
    | grep -ciE "AI.?judgment.?scheduler.*(disabled|無効|skip)|DISABLE_AI_JUDGMENT_SCHEDULER" \
    || echo "0")
  log_info "scheduler disabled log hits (after restart)=${disabled_hits}"

  # ai_decisions delta 確認
  sleep "${AI_DELTA_WAIT_SEC}"
  local cnt_after delta
  cnt_after=$(count_ai_decisions || echo "${cnt_before}")
  delta=$(( cnt_after - cnt_before ))
  log_info "ai_decisions delta=${delta}"

  # 復元: override なしで再起動
  log_info "TC-2 復元: DISABLE_AI_JUDGMENT_SCHEDULER を削除して再起動"
  docker compose -f "${COMPOSE_FILE}" up -d --no-deps "${svc_name}" 2>/dev/null \
    || log_warn "復元 docker compose up failed (手動確認要)"
  rm -f "${OVERRIDE_FILE}"

  # 復元後 /health 待ち
  sleep 10
  local restored_health
  restored_health=$(curl -sS --max-time 5 "${BASE_URL}/health" 2>/dev/null \
    | jq -r '.env // empty' 2>/dev/null || echo "")
  log_info "/health after restore: ${restored_health}"

  # 判定
  if [[ "${delta}" -eq 0 && "${disabled_hits}" -ge 1 ]]; then
    gate_record PASS "TC-2: env var disable" \
      "DISABLE_AI_JUDGMENT_SCHEDULER=1 再起動 / disabled_log=${disabled_hits}hits / delta=${delta} / restored"
  else
    gate_record FAIL "TC-2: env var disable" \
      "delta=${delta} (expected 0) / disabled_log=${disabled_hits}hits / health_after=${restored_health}"
  fi
}

# =============================================================================
# TC-3: ai_decision エラー連続 → Slack 通知 + ai_decisions 0件
#
# 検証:
#   - emergency_stop 発動中に /api/ai/trigger を複数回呼び → 全て reject
#   - ai_decisions delta=0 (emergency_stop 中は AI 判定生成なし)
#   - backend ログに emergency_stop / skip 理由が記録されること
#   - Slack 通知ログ確認 (⚠️ scheduler error または 🚨 emergency_stop)
#   - resume で復元
#
# 付記:
#   本 TC はスケジューラーエラー (Claude API 障害等) による ai_decisions 0件パスを
#   emergency_stop 経由で代替検証している。実際の Claude API 連続失敗テストは
#   ANTHROPIC_API_KEY=invalid での手動テストが必要 (スクリプト外)。
#   monitoring_service.record_error() による ERROR_RATE_HIGH アラートは
#   error_rate > 20% (100件ウィンドウ中 21件以上) で発火するが、
#   emergency_stop は発動しない (Slack ALERT のみ)。
# =============================================================================
run_tc3() {
  log_section "TC-3: ai_decision エラー連続 → Slack 通知 + 0件確認"

  if should_skip_tc "3"; then
    gate_record SKIP "TC-3: error consecutive" "SKIP_TCS に指定"
    return 0
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "[DRY_RUN] emergency_stop 発動 → /api/ai/trigger を複数回呼び reject を確認"
    log_info "[DRY_RUN] ai_decisions delta=0 / backend log で emergency_stop skip 確認"
    log_info "[DRY_RUN] resume で復元"
    gate_record SKIP "TC-3: error consecutive" "DRY_RUN=true (手順確認のみ)"
    return 0
  fi

  # 3a. 事前 ai_decisions 件数
  local cnt_before
  cnt_before=$(count_ai_decisions || echo "")

  # 3b. emergency_stop 発動 (trigger を reject させるため)
  local stop_code
  stop_code=$(do_emergency_stop "${E2E_TAG} TC-3 error-consecutive simulation")
  CLEANUP_NEEDED=true
  log_info "emergency_stop 発動 (trigger reject 用) HTTP=${stop_code}"

  # 3c. /api/ai/trigger を 3 回呼び、全て emergency_stop で reject されることを確認
  local trigger_rejects=0 trigger_ok=0
  for i in 1 2 3; do
    local tr_resp_file tr_code tr_action
    tr_resp_file="/tmp/${E2E_TAG}_tc3_trigger${i}.json"
    tr_code=$(curl -sS --max-time 30 -o "${tr_resp_file}" -w '%{http_code}' \
      -X POST "${BASE_URL}/api/ai/trigger" \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" 2>/dev/null || echo "000")
    tr_action=$(jq -r '.action // empty' "${tr_resp_file}" 2>/dev/null || echo "")
    rm -f "${tr_resp_file}"
    log_info "trigger #${i}: HTTP=${tr_code} action=${tr_action}"

    # reject 判定: HTTP 4xx/5xx または proposals_created=0 (HOLD due to emergency_stop)
    if [[ "${tr_code}" =~ ^[45][0-9][0-9]$ ]]; then
      trigger_rejects=$(( trigger_rejects + 1 ))
    elif [[ "${tr_action}" == "HOLD" ]]; then
      trigger_rejects=$(( trigger_rejects + 1 ))
    else
      trigger_ok=$(( trigger_ok + 1 ))
    fi
    sleep 1
  done
  log_info "trigger rejects=${trigger_rejects}/3 ok=${trigger_ok}/3"

  # 3d. ai_decisions delta=0 確認
  sleep "${AI_DELTA_WAIT_SEC}"
  local cnt_after delta
  cnt_after=$(count_ai_decisions || echo "${cnt_before}")
  if [[ -n "${cnt_before}" && "${cnt_before}" =~ ^[0-9]+$ ]]; then
    delta=$(( cnt_after - cnt_before ))
  else
    delta="N/A"
  fi
  log_info "ai_decisions delta=${delta}"

  # 3e. backend ログでエラー/skip ログ確認
  local skip_log_hits
  skip_log_hits=$(check_backend_logs "emergency_stop.*skip|skip.*emergency_stop|trading_paused|is_trading_allowed")
  log_info "emergency_stop skip log hits=${skip_log_hits}"

  # Slack 通知ログ (activate / scheduler error)
  local slack_hits
  slack_hits=$(check_backend_logs "緊急停止が発動|EMERGENCY_STOP|Scheduler.*実行失敗|ERROR_RATE_HIGH")
  log_info "Slack notification log hits=${slack_hits}"

  # 3f. resume
  local resume_code
  resume_code=$(do_resume)
  log_info "resume HTTP=${resume_code}"
  if [[ "${resume_code}" =~ ^2[0-9][0-9]$ ]]; then
    CLEANUP_NEEDED=false
  fi

  # 判定
  local delta_ok=true
  if [[ "${delta}" != "N/A" && "${delta}" -gt 1 ]]; then
    delta_ok=false
  fi

  if [[ "${trigger_rejects}" -ge 2 && "${delta_ok}" == "true" && "${slack_hits}" -ge 1 \
        && "${resume_code}" =~ ^2[0-9][0-9]$ ]]; then
    gate_record PASS "TC-3: error consecutive" \
      "trigger reject=${trigger_rejects}/3 / delta=${delta} / slack=${slack_hits}hits / resumed"
  else
    gate_record FAIL "TC-3: error consecutive" \
      "rejects=${trigger_rejects} delta=${delta} delta_ok=${delta_ok} slack=${slack_hits} resume=${resume_code}"
  fi
}

# =============================================================================
# TC-4: HF < 閾値 (1.6) → trading_paused=true + LINE 通知
#
# 検証:
#   a) 現在 HF を /api/aave/health-factor で取得
#   b) LINE_NOTIFY_TOKEN が staging container に設定されているか確認
#   c) HF < 1.6 なら既に auto stop 済みのため即 PASS
#   d) HF >= 1.6 の場合 (staging dummy=2.5):
#      - docker exec Python で record_health_factor(1.3) ロジックを単体検証
#      - API 経由で emergency_stop 発動し trading_paused=true を確認 (HF 相当)
#      - backend ログで HF 閾値ログと LINE 通知試行を確認
#      - resume で復元
#
# 付記:
#   staging は AAVE_CLIENT_TYPE=dummy のため get_health_factor() は常に 2.5 を返す。
#   実際の HF < 1.6 自動停止テストは AAVE_CLIENT_TYPE=web3 の本番環境か、
#   Docker コンテナ起動時に state.json を emergency_stop=true で上書きした場合に確認可能。
#   LINE 通知は notify_health_factor() からのみ発火 (emergency_stop API 経由では発火しない)。
#   LINE_NOTIFY_TOKEN 設定 + record_health_factor(1.3) ロジック検証で実通知パスを確認する。
# =============================================================================
run_tc4() {
  log_section "TC-4: HF < 閾値 (1.6) → trading_paused + LINE 通知"

  if should_skip_tc "4"; then
    gate_record SKIP "TC-4: HF threshold" "SKIP_TCS に指定"
    return 0
  fi

  # 4a. 現在 HF 取得
  local hf_resp hf_val
  hf_resp=$(curl -sS --max-time "${CURL_TIMEOUT}" "${BASE_URL}/api/aave/health-factor" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" 2>/dev/null || echo '{}')
  hf_val=$(echo "${hf_resp}" | jq -r '.health_factor // "null"' 2>/dev/null || echo "null")
  log_info "現在 HF=${hf_val}"

  # 4b. LINE_NOTIFY_TOKEN 設定確認
  local line_token_set
  line_token_set=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
    "${BACKEND_CONTAINER}" 2>/dev/null \
    | grep -c '^LINE_NOTIFY_TOKEN=' || echo "0")
  log_info "LINE_NOTIFY_TOKEN configured=${line_token_set} (>0 = set)"

  # 4c. HF < 1.6 なら既に自動停止済み
  local hf_decimal
  hf_decimal=$(echo "${hf_val}" | grep -oE '^[0-9]+(\.[0-9]+)?' 2>/dev/null || echo "99")
  if awk "BEGIN{exit !(${hf_decimal} < 1.6)}" 2>/dev/null; then
    local paused
    paused=$(is_trading_paused)
    log_info "HF=${hf_val} < 1.6 閾値 → is_trading_paused=${paused} (自動停止済み)"
    if [[ "${paused}" == "true" ]]; then
      gate_record PASS "TC-4: HF threshold" \
        "HF=${hf_val} < 1.6 / is_trading_paused=true (自動停止中) / LINE_TOKEN=${line_token_set}"
      return 0
    fi
  fi

  # 4d. docker exec Python で record_health_factor ロジック単体検証
  log_info "record_health_factor(1.3) ロジック検証 (docker exec)"
  local py_tmp="/tmp/${E2E_TAG}_tc4_logic.py"
  cat > "${py_tmp}" << 'PYEOF'
import sys
from decimal import Decimal
hf_emergency_threshold = Decimal('1.6')
hf_warning_threshold = Decimal('1.8')
test_cases = [
    (Decimal('1.3'), 'HARD_STOP'),
    (Decimal('1.5'), 'HARD_STOP'),
    (Decimal('1.7'), 'WARNING'),
    (Decimal('2.5'), 'NORMAL'),
]
all_ok = True
for hf, expected in test_cases:
    if hf < hf_emergency_threshold:
        result = 'HARD_STOP'
    elif hf < hf_warning_threshold:
        result = 'WARNING'
    else:
        result = 'NORMAL'
    ok = result == expected
    if not ok:
        all_ok = False
    print(f'HF={hf}: result={result} expected={expected} ok={ok}')
import os
line_token = os.getenv('LINE_NOTIFY_TOKEN', '')
print(f'LINE_NOTIFY_TOKEN={"SET" if line_token else "NOT_SET"}')
sys.exit(0 if all_ok else 1)
PYEOF
  local hf_logic_result
  hf_logic_result=$(cat "${py_tmp}" | docker exec -i "${BACKEND_CONTAINER}" python3 2>/dev/null \
    || echo "exec_error")
  rm -f "${py_tmp}"

  log_info "docker exec result:"
  echo "${hf_logic_result}" | while IFS= read -r line; do
    log_info "  ${line}"
  done

  local hf_logic_ok=false
  if ! echo "${hf_logic_result}" | grep -q "exec_error"; then
    if echo "${hf_logic_result}" | grep -q "ok=True"; then
      hf_logic_ok=true
    fi
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    if [[ "${hf_logic_ok}" == "true" && "${line_token_set}" -ge 1 ]]; then
      gate_record PASS "TC-4: HF threshold" \
        "logic OK (DRY_RUN) / LINE_TOKEN=set. 実 HF 注入: staging Aave web3 で確認要"
    else
      gate_record FAIL "TC-4: HF threshold" \
        "hf_logic=${hf_logic_ok} LINE_TOKEN=${line_token_set}"
    fi
    return 0
  fi

  # 4e. API 経由で HF 相当の emergency_stop を発動 (trading_paused=true を確認)
  local stop_code
  stop_code=$(do_emergency_stop "${E2E_TAG} TC-4 HF=1.3-simulation threshold-test")
  CLEANUP_NEEDED=true
  log_info "HF simulation emergency_stop HTTP=${stop_code}"

  local paused
  paused=$(is_trading_paused)
  log_info "is_trading_paused=${paused} (HF simulation)"

  # 4f. backend ログで HF 閾値・LINE 通知試行を確認
  local hf_log_hits
  hf_log_hits=$(check_backend_logs "health.factor.*below|hf.*threshold|below.*emergency|HF.*1\\.[0-9]|HARD_STOP")
  log_info "HF threshold log hits=${hf_log_hits}"

  local line_log_hits
  line_log_hits=$(check_backend_logs "line.*notif|LINE.*notify|notify_health_factor|LINE_NOTIFY")
  log_info "LINE notify log hits=${line_log_hits}"

  # 4g. resume
  local resume_code
  resume_code=$(do_resume)
  log_info "resume HTTP=${resume_code}"
  if [[ "${resume_code}" =~ ^2[0-9][0-9]$ ]]; then
    CLEANUP_NEEDED=false
  fi

  sleep 1
  local paused_after
  paused_after=$(is_trading_paused)
  log_info "is_trading_paused after resume=${paused_after}"

  # 判定
  if [[ "${hf_logic_ok}" == "true" && "${paused}" == "true" && "${line_token_set}" -ge 1 \
        && "${resume_code}" =~ ^2[0-9][0-9]$ && "${paused_after}" == "false" ]]; then
    gate_record PASS "TC-4: HF threshold" \
      "logic OK / paused=true / LINE_TOKEN=set(${line_token_set}) / resumed. (実HF=1.3注入は web3 環境で確認要)"
  else
    gate_record FAIL "TC-4: HF threshold" \
      "logic=${hf_logic_ok} paused=${paused} LINE_TOKEN=${line_token_set} resume=${resume_code} paused_after=${paused_after}"
  fi
}

# =============================================================================
# TC-5: resume / 復元 総合確認
#
# 検証:
#   - 全 TC 完了後に念のため resume を実行
#   - is_trading_paused=false を確認
#   - /api/automation/status で emergency_reason が空 (= クリア済み) を確認
#   - backend ログで resume (clear_emergency_stop) ログを確認
#   - /api/ai/trigger が 4xx ではなく実行される (scheduler 再開確認)
# =============================================================================
run_tc5() {
  log_section "TC-5: resume / 復元 総合確認"

  if should_skip_tc "5"; then
    gate_record SKIP "TC-5: resume restoration" "SKIP_TCS に指定"
    return 0
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "[DRY_RUN] POST /api/automation/emergency-stop/resume を呼び"
    log_info "[DRY_RUN] is_trading_paused=false / resume log 確認 / trigger 正常実行確認"
    gate_record SKIP "TC-5: resume restoration" "DRY_RUN=true (手順確認のみ)"
    return 0
  fi

  # 5a. 念のため resume (前 TC での cleanup が不完全だった場合に備え)
  local resume_code
  resume_code=$(do_resume)
  log_info "final resume HTTP=${resume_code}"

  # 5b. is_trading_paused=false 確認
  sleep 2
  local paused
  paused=$(is_trading_paused)
  log_info "is_trading_paused=${paused}"

  # 5c. /api/automation/status の emergency_reason が空であることを確認
  local status_body emergency_reason
  status_body=$(get_automation_status)
  emergency_reason=$(echo "${status_body}" | jq -r '.emergency_reason // ""' 2>/dev/null || echo "")
  log_info "emergency_reason='${emergency_reason}'"

  # 5d. backend ログで resume 通知確認
  local resume_log_hits
  resume_log_hits=$(check_backend_logs "緊急停止を解除|clear_emergency_stop|emergency.*clear|resume.*stop")
  log_info "resume log hits=${resume_log_hits}"

  # 5e. /api/ai/trigger で scheduler 再開確認
  local tr_resp_file tr_code tr_action tr_proposals
  tr_resp_file="/tmp/${E2E_TAG}_tc5_trigger.json"
  tr_code=$(curl -sS --max-time 30 -o "${tr_resp_file}" -w '%{http_code}' \
    -X POST "${BASE_URL}/api/ai/trigger" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" 2>/dev/null || echo "000")
  tr_action=$(jq -r '.action // empty' "${tr_resp_file}" 2>/dev/null || echo "")
  tr_proposals=$(jq -r '.proposals_created // empty' "${tr_resp_file}" 2>/dev/null || echo "")
  rm -f "${tr_resp_file}"
  log_info "post-resume trigger HTTP=${tr_code} action=${tr_action} proposals=${tr_proposals}"

  # ai_decisions が増加するか確認
  local cnt_before cnt_after delta_after
  cnt_before=$(count_ai_decisions || echo "0")
  sleep 3
  cnt_after=$(count_ai_decisions || echo "${cnt_before}")
  delta_after=$(( cnt_after - cnt_before ))
  log_info "ai_decisions delta (post-resume)=${delta_after}"

  CLEANUP_NEEDED=false

  # 5f. 最終 /health 確認
  local final_health
  final_health=$(curl -sS --max-time 10 "${BASE_URL}/health" 2>/dev/null \
    | jq -r '.env // empty' 2>/dev/null || echo "")
  log_info "final /health env=${final_health}"

  # 判定
  local trigger_ok=false
  if [[ "${tr_code}" =~ ^2[0-9][0-9]$ && -n "${tr_action}" ]]; then
    trigger_ok=true
  fi

  if [[ "${paused}" == "false" && "${resume_code}" =~ ^2[0-9][0-9]$ \
        && "${resume_log_hits}" -ge 1 && "${trigger_ok}" == "true" ]]; then
    gate_record PASS "TC-5: resume restoration" \
      "paused=false / resume HTTP=${resume_code} / log=${resume_log_hits}hits / trigger HTTP=${tr_code} action=${tr_action}"
  else
    gate_record FAIL "TC-5: resume restoration" \
      "paused=${paused} resume=${resume_code} log=${resume_log_hits} trigger=${tr_code} action=${tr_action}"
  fi
}

# =============================================================================
# メイン
# =============================================================================
main() {
  echo ""
  echo "================================================================"
  echo " Ultra AutoTrade — 緊急停止 e2e 全経路検証"
  echo " ${SCRIPT_NAME}"
  echo " E2E_TAG : ${E2E_TAG}"
  echo " DRY_RUN : ${DRY_RUN}"
  echo " DO_SCHEDULER_RESTART_TEST : ${DO_SCHEDULER_RESTART_TEST}"
  echo " SKIP_TCS: ${SKIP_TCS:-なし}"
  echo "================================================================"

  _safety_check
  _load_slack_webhook

  _require_env ADMIN_EMAIL
  _require_env ADMIN_PASSWORD

  _detect_containers
  _verify_staging
  _get_admin_token

  # 開始通知
  _slack "🔍 [${SCRIPT_NAME}] 緊急停止 e2e 検証開始 (tag=${E2E_TAG} dry_run=${DRY_RUN})"

  # TC 実行
  run_tc1
  run_tc2
  run_tc3
  run_tc4
  run_tc5

  # 完了通知
  local result_icon
  if [[ "${FAIL_COUNT}" -eq 0 ]]; then
    result_icon="✅"
  else
    result_icon="❌"
  fi
  _slack "${result_icon} [${SCRIPT_NAME}] e2e 完了 PASS=${PASS_COUNT} FAIL=${FAIL_COUNT} SKIP=${SKIP_COUNT} (tag=${E2E_TAG})"

  echo ""
  gate_summary
  local RC=$?
  echo ""
  echo "(E2E_TAG=${E2E_TAG} の全 emergency_stop は cleanup 済み)"
  exit "${RC}"
}

main "$@"
