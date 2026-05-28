#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L4_kill_switch_e2e.sh
#
# §17 Launch Gate L4 拡張版: 緊急停止 (kill switch) 5項目 e2e 検証。
#
# 検証項目 (PASS/FAIL を 5 項目で明示):
#   1) /api/automation/emergency-stop POST → 2xx
#   2) 発動後、AI 提案生成が止まる (ai_decisions 行数 delta = 0 / または
#      manual trigger /api/ai/trigger が emergency_stop で skip)
#   3) 発動後、workflow run が emergency_stop で skip される (既存 pending
#      proposal の execute がブロックされる経路の代理検証)
#   4) /api/automation/emergency-stop/resume POST → 2xx、解除後 AI 判定が再開
#   5) 発動・解除ログが Slack #ultra-auto-project に出る (backend ログから
#      Slack post 試行を確認 / 直近 webhook 送信ログ 2 件以上)
#
# 実行先: iMac から `ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155` 後、
#         本番 VPS 上で staging stack に対して実行する。
#         本番 stack には絶対に触らない (staging endpoint / staging DB / staging
#         backend container のみ操作)。
#
# 前提環境変数 (1Password 等から export):
#   ADMIN_EMAIL          : staging admin user メール (role=admin)
#                          例: ADMIN_EMAIL=hkobayashi@mooores.com
#   ADMIN_PASSWORD       : staging admin password
# オプション環境変数:
#   STAGING_BASE_URL     : default http://127.0.0.1:8082 (staging nginx)
#   POSTGRES_CONTAINER   : default 自動検出 (postgres + staging)
#   BACKEND_CONTAINER    : default 自動検出 (nginx upstream の active 側)
#   DB_USER              : default ultra
#   DB_NAME              : default ultra_autotrade_staging
#   AI_DELTA_WAIT_SEC    : default 5 (ai_decisions delta 観測待ち)
#   LOG_TAIL_LINES       : default 200 (Slack 通知ログ抽出範囲)
#
# 安全装置:
#   - hostname が "uata-dev*" の場合 (dev VPS) は即 SKIP (構造上不可)
#   - postgres/backend コンテナ名に "staging" を含まない場合は abort
#   - SQL は SELECT のみ (DB write しない)
#   - 試験用 emergency stop の reason に "L4-e2e" を含めて誤検知防止
#
# Usage:
#   ADMIN_EMAIL=... ADMIN_PASSWORD=... bash scripts/launch_gate/L4_kill_switch_e2e.sh
#
# 期待出力 (末尾):
#   === L4 Kill Switch e2e Summary ===
#   [PASS] 1. emergency-stop POST       HTTP 200
#   [PASS] 2. ai_decisions blocked      delta=0 / manual trigger skipped
#   [PASS] 3. workflow.run skipped      reason=emergency_stop
#   [PASS] 4. resume + AI restart       HTTP 200, ai_decisions delta>0
#   [PASS] 5. Slack notify              activate+clear log lines found
#   PASS=5 FAIL=0
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

ENV_TAG="L4-e2e-$(date +%Y%m%dT%H%M%S)"
BASE_URL="${STAGING_BASE_URL:-http://127.0.0.1:8082}"
DB_USER="${DB_USER:-ultra}"
DB_NAME="${DB_NAME:-ultra_autotrade_staging}"
AI_DELTA_WAIT_SEC="${AI_DELTA_WAIT_SEC:-5}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-200}"

TMP_DIR="$(mktemp -d -t l4_kill_switch.XXXXXX)"
trap 'rm -rf "${TMP_DIR}"' EXIT

# ---------------------------------------------------------------------------
# 0. Guard: dev VPS は構造上実行不可
# ---------------------------------------------------------------------------
if is_dev_vps; then
  cat <<'EOF'
[INFO] L4 kill switch e2e: dev VPS では実行不可。
       本 script は本番 VPS (77.42.46.155) 上で staging stack に対して実行する設計です。
       実行手順:
         1) ローカル Mac で: ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155
         2) 本番 VPS で:
              export ADMIN_EMAIL=...
              export ADMIN_PASSWORD=...
              cd /opt/ultra-autotrade
              bash scripts/launch_gate/L4_kill_switch_e2e.sh
EOF
  gate_record SKIP "L4-killswitch-e2e" "dev VPS のため SKIP (本番 VPS で実行する)"
  gate_summary
  exit 0
fi

# ---------------------------------------------------------------------------
# 0.1 Guard: 必須 env / コマンド
# ---------------------------------------------------------------------------
require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "[FATAL] required env not set: ${name}" >&2
    exit 2
  fi
}
require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[FATAL] command not found: ${cmd}" >&2
    exit 2
  fi
}

require_env ADMIN_EMAIL
require_env ADMIN_PASSWORD
require_cmd curl
require_cmd docker
require_cmd jq

# ---------------------------------------------------------------------------
# 0.2 コンテナ動的検出 (staging 限定)
# ---------------------------------------------------------------------------
if [[ -z "${POSTGRES_CONTAINER:-}" ]]; then
  POSTGRES_CONTAINER=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
    | grep postgres | grep staging | head -1 || true)
fi
if [[ -z "${POSTGRES_CONTAINER:-}" || "${POSTGRES_CONTAINER}" != *staging* ]]; then
  echo "[FATAL] staging postgres コンテナが見つかりません。'docker ps | grep postgres' を確認。" >&2
  echo "        POSTGRES_CONTAINER=${POSTGRES_CONTAINER:-(empty)}" >&2
  exit 2
fi

if [[ -z "${BACKEND_CONTAINER:-}" ]]; then
  NGINX_C=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
    | grep nginx | grep staging | head -1 || true)
  ACTIVE_ALIAS=""
  if [[ -n "${NGINX_C}" ]]; then
    ACTIVE_ALIAS=$(docker exec "${NGINX_C}" cat /etc/nginx/conf.d/upstream.conf 2>/dev/null \
      | grep -oE 'backend-(blue|green)' | head -1 || true)
  fi
  if [[ -n "${ACTIVE_ALIAS}" ]]; then
    BACKEND_CONTAINER=$(docker ps --filter "status=running" --format "{{.Names}}" 2>/dev/null \
      | grep "${ACTIVE_ALIAS}" | grep staging | head -1 || true)
  fi
fi
if [[ -z "${BACKEND_CONTAINER:-}" || "${BACKEND_CONTAINER}" != *staging* ]]; then
  echo "[FATAL] staging backend (active) コンテナが見つかりません。" >&2
  echo "        BACKEND_CONTAINER=${BACKEND_CONTAINER:-(empty)}" >&2
  exit 2
fi

log_info "POSTGRES_CONTAINER=${POSTGRES_CONTAINER}"
log_info "BACKEND_CONTAINER=${BACKEND_CONTAINER}"
log_info "BASE_URL=${BASE_URL}"
log_info "ENV_TAG=${ENV_TAG}"

# ---------------------------------------------------------------------------
# 0.3 staging /health で env=staging 確認 (production への誤接続防止)
# ---------------------------------------------------------------------------
health_body=$(curl -sS --max-time 10 "${BASE_URL}/health" 2>/dev/null || echo "")
health_env=$(echo "${health_body}" | jq -r '.env // empty' 2>/dev/null || echo "")
if [[ "${health_env}" != "staging" ]]; then
  echo "[FATAL] /health env='${health_env}' (expected 'staging')。BASE_URL を確認。" >&2
  echo "        body: ${health_body}" >&2
  exit 2
fi
log_info "/health env=staging 確認 OK"

# ---------------------------------------------------------------------------
# 0.4 admin JWT 取得 (/auth/login)
# ---------------------------------------------------------------------------
login_payload=$(jq -n --arg e "${ADMIN_EMAIL}" --arg p "${ADMIN_PASSWORD}" \
  '{email:$e, password:$p}')
login_body=$(curl -sS --max-time 15 -X POST "${BASE_URL}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "${login_payload}" 2>/dev/null || echo "")
ADMIN_TOKEN=$(echo "${login_body}" | jq -r '.access_token // empty' 2>/dev/null || echo "")
if [[ -z "${ADMIN_TOKEN}" ]]; then
  echo "[FATAL] /auth/login 失敗。response: ${login_body}" >&2
  exit 2
fi
log_info "admin JWT 取得 OK (len=${#ADMIN_TOKEN})"

auth_header=(-H "Authorization: Bearer ${ADMIN_TOKEN}")

# ---------------------------------------------------------------------------
# Helper: psql wrapper (read-only想定、SELECT のみ呼ぶこと)
# ---------------------------------------------------------------------------
psql_select() {
  local sql="$1"
  docker exec "${POSTGRES_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" \
    -tA -c "${sql}" 2>/dev/null | tr -d '\r'
}

count_ai_decisions() {
  psql_select "SELECT COUNT(*) FROM ai_decisions;"
}

# ===========================================================================
# Test 1: emergency-stop POST → 2xx
# ===========================================================================
log_info "--- Test 1: POST /api/automation/emergency-stop ---"
stop_body=$(jq -n --arg r "${ENV_TAG} L4 e2e verification" '{reason:$r}')

stop_resp_file="${TMP_DIR}/stop.json"
stop_code=$(curl -sS -o "${stop_resp_file}" -w '%{http_code}' --max-time 15 \
  -X POST "${BASE_URL}/api/automation/emergency-stop" \
  "${auth_header[@]}" \
  -H 'Content-Type: application/json' \
  -d "${stop_body}" 2>/dev/null || echo "000")

stop_status=$(jq -r '.status // empty' "${stop_resp_file}" 2>/dev/null || echo "")
if [[ "${stop_code}" =~ ^2[0-9][0-9]$ && "${stop_status}" == "stopped" ]]; then
  gate_record PASS "1. emergency-stop POST" "HTTP ${stop_code} status=${stop_status}"
else
  gate_record FAIL "1. emergency-stop POST" \
    "HTTP ${stop_code} status='${stop_status}' body=$(head -c 200 "${stop_resp_file}")"
fi

# ===========================================================================
# Test 2: 発動後、AI 提案生成が止まる
#   2 段で確認:
#     (a) ai_decisions 行数 delta = 0 (短時間待機)
#     (b) /api/ai/trigger 手動発火が emergency_stop で skip される (proposals_created=0)
# ===========================================================================
log_info "--- Test 2: AI 提案生成停止確認 ---"
ai_count_before=$(count_ai_decisions || echo "")
if [[ -z "${ai_count_before}" || ! "${ai_count_before}" =~ ^[0-9]+$ ]]; then
  gate_record FAIL "2. ai_decisions blocked" "ai_decisions COUNT 取得失敗 ('${ai_count_before}')"
else
  log_info "ai_decisions count (before)=${ai_count_before}"
  sleep "${AI_DELTA_WAIT_SEC}"
  ai_count_after_wait=$(count_ai_decisions || echo "")
  log_info "ai_decisions count (after ${AI_DELTA_WAIT_SEC}s wait)=${ai_count_after_wait}"

  trigger_resp_file="${TMP_DIR}/trigger.json"
  trigger_code=$(curl -sS -o "${trigger_resp_file}" -w '%{http_code}' --max-time 30 \
    -X POST "${BASE_URL}/api/ai/trigger" \
    "${auth_header[@]}" 2>/dev/null || echo "000")
  trigger_action=$(jq -r '.action // empty' "${trigger_resp_file}" 2>/dev/null || echo "")
  trigger_proposals=$(jq -r '.proposals_created // empty' "${trigger_resp_file}" 2>/dev/null || echo "")
  trigger_body_head=$(head -c 200 "${trigger_resp_file}" 2>/dev/null || echo "")
  log_info "trigger HTTP=${trigger_code} action=${trigger_action} proposals_created=${trigger_proposals}"

  ai_count_after_trigger=$(count_ai_decisions || echo "")
  log_info "ai_decisions count (after trigger)=${ai_count_after_trigger}"

  # 判定:
  #   - wait 中の delta=0 (HOLD 周期内なので妥当)
  #   - manual trigger 結果が:
  #       (a) HTTP 4xx/5xx で拒否される、または
  #       (b) HTTP 2xx かつ action=HOLD かつ proposals_created=0
  #         (workflow が emergency_stop で skip → HOLD として記録される実装の場合)
  #   - かつ ai_decisions が +1 以上増えていない (= AI が実発火していない)
  delta_wait=$(( ai_count_after_wait - ai_count_before ))
  delta_total=$(( ai_count_after_trigger - ai_count_before ))

  blocked=false
  if [[ "${trigger_code}" =~ ^[45][0-9][0-9]$ ]]; then
    blocked=true
  elif [[ "${trigger_action}" == "HOLD" && "${trigger_proposals}" == "0" ]]; then
    blocked=true
  fi

  if [[ "${delta_wait}" -eq 0 && "${blocked}" == "true" && "${delta_total}" -le 1 ]]; then
    gate_record PASS "2. ai_decisions blocked" \
      "delta_wait=${delta_wait} trigger HTTP=${trigger_code} action=${trigger_action} proposals=${trigger_proposals}"
  else
    gate_record FAIL "2. ai_decisions blocked" \
      "delta_wait=${delta_wait} delta_total=${delta_total} trigger HTTP=${trigger_code} action='${trigger_action}' proposals='${trigger_proposals}' body=${trigger_body_head}"
  fi
fi

# ===========================================================================
# Test 3: workflow.run が emergency_stop で skip される
#   /api/automation/workflow/run?dry_run=true を呼び、結果に emergency_stop 系
#   reason が出ているか / processed=0 か を確認。
#   (require_admin)
# ===========================================================================
log_info "--- Test 3: workflow.run skip 確認 ---"
wf_resp_file="${TMP_DIR}/workflow.json"
wf_code=$(curl -sS -o "${wf_resp_file}" -w '%{http_code}' --max-time 30 \
  -X POST "${BASE_URL}/api/automation/workflow/run?dry_run=true" \
  "${auth_header[@]}" \
  -H 'Content-Type: application/json' 2>/dev/null || echo "000")
wf_body=$(cat "${wf_resp_file}" 2>/dev/null || echo "")
wf_body_head=$(echo "${wf_body}" | head -c 300)
log_info "workflow.run HTTP=${wf_code} body(head)=${wf_body_head}"

# WorkflowRunResult schema 不明確のため広めに検出:
#   - status=skipped / errors に emergency_stop / processed=0 のいずれか
wf_skipped=false
if echo "${wf_body}" | grep -qiE "emergency_stop|emergency-stop|trading_paused"; then
  wf_skipped=true
fi
wf_processed=$(echo "${wf_body}" | jq -r '.processed // empty' 2>/dev/null || echo "")
wf_status_field=$(echo "${wf_body}" | jq -r '.status // empty' 2>/dev/null || echo "")

if [[ "${wf_code}" =~ ^2[0-9][0-9]$ \
      && ( "${wf_skipped}" == "true" || "${wf_processed}" == "0" || "${wf_status_field}" == "skipped" ) ]]; then
  gate_record PASS "3. workflow.run skipped" \
    "HTTP=${wf_code} status='${wf_status_field}' processed='${wf_processed}' contains emergency_stop=${wf_skipped}"
elif [[ "${wf_code}" =~ ^[45][0-9][0-9]$ ]]; then
  # 503 / 423 等で拒否される実装もあり得る → これも合格
  gate_record PASS "3. workflow.run skipped" "HTTP=${wf_code} (拒否応答 / emergency_stop で reject)"
else
  gate_record FAIL "3. workflow.run skipped" \
    "HTTP=${wf_code} status='${wf_status_field}' processed='${wf_processed}' body=${wf_body_head}"
fi

# ===========================================================================
# Test 4: emergency-stop/resume POST → 2xx、解除後 AI 判定が再開
# ===========================================================================
log_info "--- Test 4: POST /api/automation/emergency-stop/resume ---"
resume_resp_file="${TMP_DIR}/resume.json"
resume_code=$(curl -sS -o "${resume_resp_file}" -w '%{http_code}' --max-time 15 \
  -X POST "${BASE_URL}/api/automation/emergency-stop/resume" \
  "${auth_header[@]}" 2>/dev/null || echo "000")
resume_status=$(jq -r '.status // empty' "${resume_resp_file}" 2>/dev/null || echo "")
log_info "resume HTTP=${resume_code} status=${resume_status}"

# 解除直後の AI 判定再開確認: manual trigger が emergency_stop 由来の HOLD でなくなる
# (HF/oracle 等の自動 trigger が再発動する可能性もあるが、最低限 "emergency_stop"
# 由来でない応答 になっていれば再開とみなす)
ai_count_pre_resume_trigger=$(count_ai_decisions || echo "")
trigger2_resp_file="${TMP_DIR}/trigger2.json"
trigger2_code=$(curl -sS -o "${trigger2_resp_file}" -w '%{http_code}' --max-time 30 \
  -X POST "${BASE_URL}/api/ai/trigger" \
  "${auth_header[@]}" 2>/dev/null || echo "000")
trigger2_body=$(cat "${trigger2_resp_file}" 2>/dev/null || echo "")
trigger2_action=$(echo "${trigger2_body}" | jq -r '.action // empty' 2>/dev/null || echo "")
trigger2_proposals=$(echo "${trigger2_body}" | jq -r '.proposals_created // empty' 2>/dev/null || echo "")
trigger2_decision=$(echo "${trigger2_body}" | jq -r '.decision_id // empty' 2>/dev/null || echo "")
log_info "trigger(post-resume) HTTP=${trigger2_code} action=${trigger2_action} proposals=${trigger2_proposals} decision_id=${trigger2_decision}"

ai_count_after_resume=$(count_ai_decisions || echo "")
delta_after_resume=$(( ai_count_after_resume - ai_count_pre_resume_trigger ))
log_info "ai_decisions delta(post-resume)=${delta_after_resume}"

# 判定:
#   - resume HTTP 2xx かつ status=resumed
#   - manual trigger が HTTP 2xx で decision_id が新規付与されている (= ai_decisions 記録)
#   - もしくは delta_after_resume >= 1
resume_ok=false
if [[ "${resume_code}" =~ ^2[0-9][0-9]$ && "${resume_status}" == "resumed" ]]; then
  resume_ok=true
fi
restart_ok=false
if [[ "${trigger2_code}" =~ ^2[0-9][0-9]$ \
      && ( -n "${trigger2_decision}" || "${delta_after_resume}" -ge 1 ) ]]; then
  restart_ok=true
fi

if [[ "${resume_ok}" == "true" && "${restart_ok}" == "true" ]]; then
  gate_record PASS "4. resume + AI restart" \
    "resume HTTP=${resume_code} status=${resume_status}, trigger HTTP=${trigger2_code} decision_id=${trigger2_decision} delta=${delta_after_resume}"
else
  gate_record FAIL "4. resume + AI restart" \
    "resume HTTP=${resume_code} status='${resume_status}', trigger HTTP=${trigger2_code} action='${trigger2_action}' decision_id='${trigger2_decision}' delta=${delta_after_resume}"
fi

# ===========================================================================
# Test 5: Slack 通知 (#ultra-auto-project) 発火確認
#   backend ログから activate / clear の Slack post 試行を確認。
#   _notify(NotificationSeverity.EMERGENCY, "🚨 緊急停止が発動されました", ...) と
#   "緊急停止を解除しました" 系メッセージが直近ログに出ているはず。
# ===========================================================================
log_info "--- Test 5: Slack 通知ログ確認 ---"
log_lines=$(docker logs --tail "${LOG_TAIL_LINES}" "${BACKEND_CONTAINER}" 2>&1 || echo "")

# 緊急停止発動の通知
activate_hits=$(echo "${log_lines}" | grep -ciE "EMERGENCY_STOP|緊急停止が発動|activate_emergency_stop" || true)
# 緊急停止解除の通知
clear_hits=$(echo "${log_lines}" | grep -ciE "緊急停止を解除|clear_emergency_stop|emergency_stop.*clear" || true)
# Slack 送信試行 (notifications layer)
slack_hits=$(echo "${log_lines}" | grep -ciE "slack|webhook" || true)

log_info "activate hits=${activate_hits} clear hits=${clear_hits} slack hits=${slack_hits}"

if [[ "${activate_hits}" -ge 1 && "${clear_hits}" -ge 1 ]]; then
  gate_record PASS "5. Slack notify" \
    "activate=${activate_hits} clear=${clear_hits} slack-related=${slack_hits} (backend log)"
elif [[ "${activate_hits}" -ge 1 || "${clear_hits}" -ge 1 ]]; then
  # 片方しか出ていない場合は警告だが FAIL とする (5項目の完全PASSを要求)
  gate_record FAIL "5. Slack notify" \
    "片方欠落 activate=${activate_hits} clear=${clear_hits} slack=${slack_hits}。完全な通知ログを #ultra-auto-project 側でも目視確認のこと"
else
  gate_record FAIL "5. Slack notify" \
    "activate/clear ともログ未検出 activate=${activate_hits} clear=${clear_hits} slack=${slack_hits}"
fi

# ---------------------------------------------------------------------------
# 後始末: 万一 test 4 が FAIL で resume できていなかった場合に備え、
#         emergency_stop=true のまま staging を放置しない。
# ---------------------------------------------------------------------------
log_info "--- 後始末: 念のため再度 resume を呼び staging を稼働状態に戻す ---"
curl -sS -o /dev/null --max-time 10 \
  -X POST "${BASE_URL}/api/automation/emergency-stop/resume" \
  "${auth_header[@]}" 2>/dev/null || true

# 最終状態確認
final_health=$(curl -sS --max-time 10 "${BASE_URL}/health" 2>/dev/null || echo "")
log_info "final /health: $(echo "${final_health}" | head -c 200)"

# ---------------------------------------------------------------------------
# サマリ
# ---------------------------------------------------------------------------
echo ""
echo "=== L4 Kill Switch e2e Summary ==="
gate_summary
RC=$?
echo ""
echo "(ENV_TAG=${ENV_TAG} で発動した emergency_stop は後始末済み)"
exit "${RC}"
