#!/usr/bin/env bash
# scripts/healthcheck_l1_l6.sh
#
# Ultra AutoTrade L1-L6 自動ヘルスチェック
# cron: */5 * * * * /opt/ultra-autotrade/scripts/healthcheck_l1_l6.sh >> /var/log/ultra-autotrade/healthcheck.log 2>&1
#
# 環境変数:
#   SLACK_WEBHOOK_URL      Slack Webhook URL (未設定時は .env.production から読み込み)
#   HEALTH_URL_INTERNAL    内部 /health URL (default: http://127.0.0.1:8010/health)
#   HEALTH_URL_EXTERNAL    外形 /health URL (default: https://api.ultra-auto-trade.com/health)
#   POSTGRES_CONTAINER     postgres コンテナ名 (default: ultra-autotrade-postgres-production)
#   DB_USER                postgres ユーザー (default: ultra)
#   DB_NAME                postgres DB 名 (default: ultra_autotrade)
#   DRY_RUN                true の場合 Slack 通知をスキップして JSON を stdout に出力
#   FAIL_SIMULATE_L1       true の場合 L1 を強制 FAIL (テスト用)
#
# Twilio 電話エスカレーション (5連続FAIL時):
#   TWILIO_ACCOUNT_SID     Twilio Account SID
#   TWILIO_AUTH_TOKEN      Twilio Auth Token
#   TWILIO_FROM_NUMBER     発信元電話番号 (+81XXXXXXXXXX 形式)
#   TWILIO_TO_NUMBER       着信先電話番号 (+81XXXXXXXXXX 形式)
#   TWILIO_CALL_RATE_LIMIT_MIN  電話発信の最小間隔 (分, default: 30)

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
SCRIPT_NAME="healthcheck_l1_l6"
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"

# nginx 経由 (host:8000 → nginx container:8080 → active backend)
# nginx が active color (blue:8010 / green:8011) へルーティングするため、
# この URL は Blue/Green color に依存せず常に active backend の /health に到達する。
# docker-compose.production.yml: ports "8000:8080" (host→nginx container)
# 旧値 http://127.0.0.1:8010/health は backend-blue 直ポート = Blue/Green 非依存 NG
HEALTH_URL_INTERNAL="${HEALTH_URL_INTERNAL:-http://127.0.0.1:8000/health}"
HEALTH_URL_EXTERNAL="${HEALTH_URL_EXTERNAL:-https://api.ultra-auto-trade.com/health}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ultra-autotrade-postgres-production}"
DB_USER="${DB_USER:-ultra}"
DB_NAME="${DB_NAME:-ultra_autotrade}"
DRY_RUN="${DRY_RUN:-false}"
FAIL_SIMULATE_L1="${FAIL_SIMULATE_L1:-false}"
CURL_TIMEOUT=10

# L7: ディスク使用率閾値
DISK_WARN_THRESHOLD="${DISK_WARN_THRESHOLD:-80}"
DISK_CRITICAL_THRESHOLD="${DISK_CRITICAL_THRESHOLD:-90}"

# L8 (Gate 8): Loki /ready 死活監視 (P0-2 / 2026-05-17 cascade postmortem)
LOKI_READY_URL="${LOKI_READY_URL:-http://127.0.0.1:3100/ready}"

# L9: Proposal 発火レート異常検知 (P0-X2 / 2026-05-21)
# 直近1時間の proposals 件数が閾値を超えたら異常検知。
# FAIL は overall FAIL に寄与する (7分30件のような爆発的発火を即検知するため)。
# WARN は非 fatal (overall に影響しない)。
# dev VPS / psql 不在環境では psql 失敗時に WARN/skip して overall を壊さない。
PROPOSAL_RATE_WARN="${PROPOSAL_RATE_WARN:-20}"
PROPOSAL_RATE_FAIL="${PROPOSAL_RATE_FAIL:-40}"

# Twilio 電話エスカレーション設定
TWILIO_ACCOUNT_SID="${TWILIO_ACCOUNT_SID:-}"
TWILIO_AUTH_TOKEN="${TWILIO_AUTH_TOKEN:-}"
TWILIO_FROM_NUMBER="${TWILIO_FROM_NUMBER:-}"
TWILIO_TO_NUMBER="${TWILIO_TO_NUMBER:-}"
TWILIO_CALL_RATE_LIMIT_MIN="${TWILIO_CALL_RATE_LIMIT_MIN:-30}"
TWILIO_CONSECUTIVE_FAIL_THRESHOLD=5

# PASS 通知の連投防止 (1時間に1回)
LAST_PASS_FILE="${TMPDIR:-/tmp}/.last_healthcheck_pass"
LAST_FAIL_FILE="${TMPDIR:-/tmp}/.last_healthcheck_fail"
FAIL_COUNT_FILE="${TMPDIR:-/tmp}/.healthcheck_fail_count"
TWILIO_LAST_CALL_FILE="${TMPDIR:-/tmp}/.healthcheck_twilio_last_call"
PASS_COOLDOWN_SEC=3600  # 1時間

# FAIL 通知の dedup/throttle (アラート疲労対策 / 2026-06-26)
# 背景: FAIL 側は従来 throttle 無しで 5分毎に無条件送信していた。本番 P0(blue/green
# color drift で AI判定停止)では L3=FAIL が 22日間・6099回連続で Slack に送られ続け、
# 同一メッセージの洪水で #ultra-auto-project に埋没し人間が気づけなかった (検知も送信も
# 正常だったが「鳴りすぎて無視された」)。対策: 同一 failed_layers が継続する間は
# FAIL_RESEND_COOLDOWN_SEC に1回だけ再送し、状態変化(新規/解消/レイヤー変化)時は即送信。
FAIL_SIG_FILE="${TMPDIR:-/tmp}/.healthcheck_fail_sig"
FAIL_RESEND_COOLDOWN_SEC="${FAIL_RESEND_COOLDOWN_SEC:-3600}"  # 同一FAIL継続中の再送間隔 (既定1h)

# ログ
LOG_DIR="${LOG_DIR:-/var/log/ultra-autotrade}"
mkdir -p "${LOG_DIR}" 2>/dev/null || true

# =============================================================================
# Slack Webhook URL の解決
# =============================================================================
if [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && [[ -f "${ENV_FILE}" ]]; then
  SLACK_WEBHOOK_URL=$(grep "^SLACK_WEBHOOK_URL=" "${ENV_FILE}" | cut -d= -f2- | tr -d '"' || true)
fi

# =============================================================================
# ユーティリティ
# =============================================================================
timestamp_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  echo "$(timestamp_utc) [${SCRIPT_NAME}] $*" >&2
}

# psql をコンテナ経由で実行し、数値を返す
psql_count() {
  local sql="$1"
  docker exec "${POSTGRES_CONTAINER}" \
    psql -U "${DB_USER}" -d "${DB_NAME}" -t -c "${sql}" 2>/dev/null \
    | tr -d '[:space:]'
}

# =============================================================================
# チェック関数 (各自 "PASS" or "FAIL" を返す)
# =============================================================================

# L1: インフラ — 全コンテナ Up + /health 200
check_l1() {
  local details=""
  local status="PASS"

  # テスト用シミュレーション
  if [[ "${FAIL_SIMULATE_L1}" == "true" ]]; then
    echo '{"status":"FAIL","details":"L1 FAIL simulated for testing"}'
    return
  fi

  # 1. docker ps で ultra-autotrade コンテナ数を確認
  local up_count
  up_count=$(docker ps --filter "name=ultra-autotrade" --filter "status=running" --format "{{.Names}}" 2>/dev/null | wc -l | tr -d '[:space:]')
  if [[ "${up_count}" -lt 7 ]]; then
    status="FAIL"
    details="${details}containers_running=${up_count}/7 "
  else
    details="${details}containers_running=${up_count}/7 "
  fi

  # 2. 内部 /health
  local http_code_internal
  http_code_internal=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout "${CURL_TIMEOUT}" --max-time "${CURL_TIMEOUT}" \
    "${HEALTH_URL_INTERNAL}" 2>/dev/null)
  http_code_internal="${http_code_internal:-000}"
  if [[ "${http_code_internal}" != "200" ]]; then
    status="FAIL"
    details="${details}internal_health=${http_code_internal} "
  else
    details="${details}internal_health=200 "
  fi

  # 3. 外形 /health
  local http_code_external
  http_code_external=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout "${CURL_TIMEOUT}" --max-time "${CURL_TIMEOUT}" \
    "${HEALTH_URL_EXTERNAL}" 2>/dev/null)
  http_code_external="${http_code_external:-000}"
  if [[ "${http_code_external}" != "200" ]]; then
    status="FAIL"
    details="${details}external_health=${http_code_external}"
  else
    details="${details}external_health=200"
  fi

  printf '{"status":"%s","details":"%s"}' "${status}" "${details}"
}

# L2: スケジューラ — scheduler_healthy + last_judgment 経過時間 < 270min
#     (AI 判定は約4時間=240min 間隔のため、60min 閾値だと正常運用でも常時 FAIL に
#      なる。docs/launch_decision_criteria_v2.md 準拠で 270min = 240 + 30 buffer)
check_l2() {
  local status="PASS"
  local scheduler_healthy="unknown"
  local last_judgment_age_min="-1"
  local warnings_count=0

  local body
  body=$(curl -sf \
    --connect-timeout "${CURL_TIMEOUT}" --max-time "${CURL_TIMEOUT}" \
    "${HEALTH_URL_INTERNAL}" 2>/dev/null || echo "")

  if [[ -z "${body}" ]]; then
    printf '{"status":"FAIL","scheduler_healthy":false,"last_judgment_age_min":-1,"details":"health endpoint unreachable"}'
    return
  fi

  # scheduler_healthy
  scheduler_healthy=$(echo "${body}" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(str(d.get('scheduler_healthy', d.get('scheduler', 'unknown'))).lower())" \
    2>/dev/null || echo "unknown")

  if [[ "${scheduler_healthy}" != "true" ]]; then
    status="FAIL"
  fi

  # last_judgment → 経過時間 (分)
  local last_judgment
  last_judgment=$(echo "${body}" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('last_judgment',''))" \
    2>/dev/null || echo "")

  if [[ -n "${last_judgment}" && "${last_judgment}" != "null" ]]; then
    last_judgment_age_min=$(python3 -c \
      "import datetime; t=datetime.datetime.fromisoformat('${last_judgment}'.replace('Z','+00:00')); \
       now=datetime.datetime.now(datetime.timezone.utc); \
       print(int((now-t).total_seconds()/60))" 2>/dev/null || echo "-1")
    if [[ "${last_judgment_age_min}" -gt 270 && "${last_judgment_age_min}" != "-1" ]]; then
      status="FAIL"
    fi
  fi

  # warnings
  warnings_count=$(echo "${body}" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(len(d.get('warnings', [])))" \
    2>/dev/null || echo "0")
  if [[ "${warnings_count}" -gt 0 ]]; then
    status="FAIL"
  fi

  printf '{"status":"%s","scheduler_healthy":%s,"last_judgment_age_min":%s,"warnings_count":%s}' \
    "${status}" "${scheduler_healthy}" "${last_judgment_age_min}" "${warnings_count}"
}

# L3: AI判定 — 24h で >= 3件
check_l3() {
  local status="PASS"
  local ai_count=0

  ai_count=$(psql_count \
    "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '24 hours';" \
    || echo "0")
  ai_count="${ai_count:-0}"

  if [[ "${ai_count}" -lt 3 ]]; then
    status="FAIL"
  fi

  printf '{"status":"%s","ai_decisions_24h":%s}' "${status}" "${ai_count}"
}

# L4: ユーザー反応 — expired 率 < 50%
check_l4() {
  local status="PASS"
  local total=0
  local expired=0
  local expired_rate=0

  total=$(psql_count \
    "SELECT COUNT(*) FROM proposals WHERE created_at > NOW() - INTERVAL '24 hours';" \
    || echo "0")
  total="${total:-0}"

  if [[ "${total}" -gt 0 ]]; then
    expired=$(psql_count \
      "SELECT COUNT(*) FROM proposals WHERE status='expired' AND created_at > NOW() - INTERVAL '24 hours';" \
      || echo "0")
    expired="${expired:-0}"

    expired_rate=$(python3 -c \
      "print(round(${expired}/${total},2))" 2>/dev/null || echo "0")

    if [[ $(python3 -c "print(1 if ${expired_rate} >= 0.5 else 0)" 2>/dev/null || echo "0") == "1" ]]; then
      status="FAIL"
    fi
  fi

  printf '{"status":"%s","proposals_24h":%s,"expired":%s,"expired_rate":%s}' \
    "${status}" "${total}" "${expired}" "${expired_rate}"
}

# L5: 実取引 — tx_hash=NULL かつ is_dry_run=false の失敗率 < 20%
check_l5() {
  local status="PASS"
  local total_real=0
  local failed_real=0
  local fail_rate=0

  total_real=$(psql_count \
    "SELECT COUNT(*) FROM transactions WHERE is_dry_run = false AND created_at > NOW() - INTERVAL '24 hours';" \
    || echo "0")
  total_real="${total_real:-0}"

  if [[ "${total_real}" -gt 0 ]]; then
    failed_real=$(psql_count \
      "SELECT COUNT(*) FROM transactions WHERE tx_hash IS NULL AND is_dry_run = false AND created_at > NOW() - INTERVAL '24 hours';" \
      || echo "0")
    failed_real="${failed_real:-0}"

    fail_rate=$(python3 -c \
      "print(round(${failed_real}/${total_real},2))" 2>/dev/null || echo "0")

    if [[ $(python3 -c "print(1 if ${fail_rate} >= 0.2 else 0)" 2>/dev/null || echo "0") == "1" ]]; then
      status="FAIL"
    fi
  fi
  # UAT中 transactions=0 は FAIL ではない (total_real=0 → status=PASS)

  printf '{"status":"%s","total_real_tx_24h":%s,"tx_failed_24h":%s,"fail_rate":%s}' \
    "${status}" "${total_real}" "${failed_real}" "${fail_rate}"
}

# L6: 収益 — zero_value portfolio_snapshots < 50% (UAT期間中は warn のみ)
check_l6() {
  local status="PASS"
  local total_snapshots=0
  local zero_value_count=0
  local zero_value_pct=0

  total_snapshots=$(psql_count \
    "SELECT COUNT(*) FROM portfolio_snapshots WHERE recorded_at > NOW() - INTERVAL '1 day';" \
    || echo "0")
  total_snapshots="${total_snapshots:-0}"

  if [[ "${total_snapshots}" -gt 0 ]]; then
    zero_value_count=$(psql_count \
      "SELECT COUNT(*) FROM portfolio_snapshots WHERE total_value_usd = 0 AND recorded_at > NOW() - INTERVAL '1 day';" \
      || echo "0")
    zero_value_count="${zero_value_count:-0}"

    zero_value_pct=$(python3 -c \
      "print(round(${zero_value_count}/${total_snapshots}*100,1))" 2>/dev/null || echo "0")

    if [[ $(python3 -c "print(1 if ${zero_value_count}/${total_snapshots} >= 0.5 else 0)" 2>/dev/null || echo "0") == "1" ]]; then
      # UAT期間中は FAIL ではなく warn (note 付き)
      status="WARN"
    fi
  fi

  printf '{"status":"%s","snapshots_24h":%s,"zero_value_count":%s,"zero_value_pct":%s,"note":"UAT期間中は常態化"}' \
    "${status}" "${total_snapshots}" "${zero_value_count}" "${zero_value_pct}"
}

# =============================================================================
# L7: ディスク使用率チェック (WARN=80%, CRITICAL=90%)
# =============================================================================
check_disk() {
  local status="PASS"
  local disk_pct=0
  local disk_used_gb="0"
  local disk_avail_gb="0"

  disk_pct=$(df / | tail -1 | awk '{gsub(/%/,""); print $5}' 2>/dev/null || echo "0")
  disk_used_gb=$(df -BG / | tail -1 | awk '{gsub(/G/,""); print $3}' 2>/dev/null || echo "0")
  disk_avail_gb=$(df -BG / | tail -1 | awk '{gsub(/G/,""); print $4}' 2>/dev/null || echo "0")

  if (( disk_pct >= DISK_CRITICAL_THRESHOLD )); then
    status="CRITICAL"
  elif (( disk_pct >= DISK_WARN_THRESHOLD )); then
    status="WARN"
  fi

  printf '{"status":"%s","disk_usage_pct":%s,"disk_used_gb":"%s","disk_avail_gb":"%s","warn_threshold":%s,"critical_threshold":%s}' \
    "${status}" "${disk_pct}" "${disk_used_gb}" "${disk_avail_gb}" \
    "${DISK_WARN_THRESHOLD}" "${DISK_CRITICAL_THRESHOLD}"
}

# =============================================================================
# L8 (Gate 8): Loki /ready 死活チェック (P0-2 / 2026-05-17 cascade postmortem)
# loki が落ちると json-file 未移行サービスが道連れになるため /ready を外形監視。
# FAIL は overall FAIL に寄与 (cascade 早期検知が目的)。
# =============================================================================
check_loki() {
  local status="PASS"
  local http_code="000"

  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "${CURL_TIMEOUT}" "${LOKI_READY_URL}" 2>/dev/null || echo "000")

  if [[ "${http_code}" != "200" ]]; then
    status="FAIL"
  fi

  printf '{"status":"%s","loki_ready_url":"%s","http_code":"%s"}' \
    "${status}" "${LOKI_READY_URL}" "${http_code}"
}

# =============================================================================
# L9: Proposal 発火レート異常検知 (P0-X2 / 2026-05-21)
# 直近1時間の proposals 件数で爆発的発火 (例: 7分30件) を早期検知する。
#
# 判定ロジック:
#   proposals_1h >= PROPOSAL_RATE_FAIL (default: 40) → FAIL → overall FAIL に寄与
#   proposals_1h >= PROPOSAL_RATE_WARN (default: 20) → WARN → overall 非 fatal (WARN 止まり)
#   proposals_1h <  PROPOSAL_RATE_WARN               → PASS
#
# フォールバック:
#   dev VPS / docker exec 失敗 / psql 不在などで件数取得不可の場合は WARN/skip を返し
#   overall を壊さない。本番環境での psql 失敗は L1 (containers check) で先に検知される。
# =============================================================================
check_proposal_rate() {
  local status="PASS"
  local proposals_1h=0
  local psql_ok=true

  proposals_1h=$(psql_count \
    "SELECT COUNT(*) FROM proposals WHERE created_at > NOW() - INTERVAL '1 hour';" \
    || echo "")

  # psql 失敗 or 空値 → フォールバック (WARN/skip、overall を壊さない)
  if [[ -z "${proposals_1h}" ]]; then
    psql_ok=false
    printf '{"status":"WARN","proposals_1h":-1,"warn":%s,"fail":%s,"note":"psql 取得失敗 — dev VPS or DB 不在のため skip (L1 で検知済みのはず)"}' \
      "${PROPOSAL_RATE_WARN}" "${PROPOSAL_RATE_FAIL}"
    return
  fi

  # 数値として評価
  if (( proposals_1h >= PROPOSAL_RATE_FAIL )); then
    status="FAIL"
  elif (( proposals_1h >= PROPOSAL_RATE_WARN )); then
    status="WARN"
  fi

  printf '{"status":"%s","proposals_1h":%s,"warn":%s,"fail":%s}' \
    "${status}" "${proposals_1h}" "${PROPOSAL_RATE_WARN}" "${PROPOSAL_RATE_FAIL}"
}

# =============================================================================
# Slack 通知
# =============================================================================
send_slack() {
  local json_payload="$1"

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY_RUN] Slack payload:"
    echo "${json_payload}"
    return 0
  fi

  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    log "SLACK_WEBHOOK_URL 未設定 — 通知スキップ"
    return 0
  fi

  curl -sf -X POST "${SLACK_WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    -d "${json_payload}" > /dev/null || log "Slack 通知送信失敗"
}

should_send_pass_notification() {
  local now
  now=$(date +%s)
  if [[ -f "${LAST_PASS_FILE}" ]]; then
    local last
    last=$(cat "${LAST_PASS_FILE}" 2>/dev/null || echo "0")
    local elapsed=$(( now - last ))
    if [[ "${elapsed}" -lt "${PASS_COOLDOWN_SEC}" ]]; then
      return 1  # まだ冷却期間中
    fi
  fi
  return 0
}

record_pass_time() {
  date +%s > "${LAST_PASS_FILE}" 2>/dev/null || true
  echo "0" > "${FAIL_COUNT_FILE}" 2>/dev/null || true
  # 復旧したら FAIL シグネチャをクリアし、次の FAIL を「状態変化=即送信」扱いにする
  rm -f "${FAIL_SIG_FILE}" 2>/dev/null || true
}

# FAIL 通知を送るべきか判定 (dedup/throttle)。
# 引数: $1 = 現在の failed_layers シグネチャ (例 "L3 ")
# 送信する条件: (a) 前回と異なるシグネチャ=状態変化/新規 (b) 前回送信から
#   FAIL_RESEND_COOLDOWN_SEC 以上経過。いずれも該当しなければ抑止 (return 1)。
# 送信決定時は新しいシグネチャ+時刻を記録する。
should_send_fail_notification() {
  local sig="$1"
  local now prev_sig prev_ts elapsed
  now=$(date +%s)
  prev_sig=""
  prev_ts=0
  if [[ -f "${FAIL_SIG_FILE}" ]]; then
    prev_sig=$(sed -n '1p' "${FAIL_SIG_FILE}" 2>/dev/null || echo "")
    prev_ts=$(sed -n '2p' "${FAIL_SIG_FILE}" 2>/dev/null || echo "0")
  fi
  [[ "${prev_ts}" =~ ^[0-9]+$ ]] || prev_ts=0
  elapsed=$(( now - prev_ts ))

  if [[ "${sig}" != "${prev_sig}" ]] || (( elapsed >= FAIL_RESEND_COOLDOWN_SEC )); then
    printf '%s\n%s\n' "${sig}" "${now}" > "${FAIL_SIG_FILE}" 2>/dev/null || true
    return 0
  fi
  return 1
}

increment_fail_count() {
  local count=0
  if [[ -f "${FAIL_COUNT_FILE}" ]]; then
    count=$(cat "${FAIL_COUNT_FILE}" 2>/dev/null || echo "0")
  fi
  count=$(( count + 1 ))
  echo "${count}" > "${FAIL_COUNT_FILE}" 2>/dev/null || true
  echo "${count}"
}

# Twilio 電話エスカレーション (5連続FAIL時のみ、L6単独FAILは対象外)
# レート制限: TWILIO_CALL_RATE_LIMIT_MIN 分に1回まで
call_twilio_phone() {
  local fail_count="$1"
  local failed_layers="${2:-L1-L5}"

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY_RUN] Twilio call would fire: fail_count=${fail_count}, layers=${failed_layers}"
    return 0
  fi

  if [[ -z "${TWILIO_ACCOUNT_SID}" || -z "${TWILIO_AUTH_TOKEN}" \
     || -z "${TWILIO_FROM_NUMBER}" || -z "${TWILIO_TO_NUMBER}" ]]; then
    log "WARN: Twilio credentials not set — phone escalation skipped"
    return 0
  fi

  # レート制限チェック
  local now; now=$(date +%s)
  if [[ -f "${TWILIO_LAST_CALL_FILE}" ]]; then
    local last_call; last_call=$(cat "${TWILIO_LAST_CALL_FILE}" 2>/dev/null || echo "0")
    local elapsed=$(( now - last_call ))
    local threshold=$(( TWILIO_CALL_RATE_LIMIT_MIN * 60 ))
    if [[ "${elapsed}" -lt "${threshold}" ]]; then
      log "Twilio 電話スキップ (レート制限: ${elapsed}s < ${threshold}s)"
      return 0
    fi
  fi

  local twiml
  twiml="<Response><Say language=\"ja-JP\" voice=\"Polly.Mizuki\">こちらはウルトラオートトレードの緊急通知です。本番環境のヘルスチェックが${fail_count}回連続で失敗しました。障害レイヤーは${failed_layers}です。緊急対応が必要です。このメッセージは自動送信です。</Say><Pause length=\"2\"/><Say language=\"ja-JP\" voice=\"Polly.Mizuki\">繰り返します。本番環境のヘルスチェックが${fail_count}回連続で失敗しました。緊急対応が必要です。</Say></Response>"

  log "Twilio 電話発信: ${TWILIO_TO_NUMBER} (連続FAIL ${fail_count}回)"

  local response
  response=$(curl -s --max-time 30 -X POST \
    "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/Calls.json" \
    -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" \
    --data-urlencode "To=${TWILIO_TO_NUMBER}" \
    --data-urlencode "From=${TWILIO_FROM_NUMBER}" \
    --data-urlencode "Twiml=${twiml}" 2>&1)

  local call_sid
  call_sid=$(echo "${response}" | python3 -c \
    "import sys, json; d=json.load(sys.stdin); print(d.get('sid',''))" 2>/dev/null || echo "")

  if [[ -n "${call_sid}" && "${call_sid}" != "" ]]; then
    log "Twilio 電話発信成功: CallSid=${call_sid}"
    date +%s > "${TWILIO_LAST_CALL_FILE}" 2>/dev/null || true
    return 0
  else
    local error_msg
    error_msg=$(echo "${response}" | python3 -c \
      "import sys, json; d=json.load(sys.stdin); print(d.get('message','unknown error'))" 2>/dev/null \
      || echo "${response}")
    log "ERROR: Twilio 電話発信失敗: ${error_msg}" >&2
    return 1
  fi
}

# =============================================================================
# メイン
# =============================================================================
main() {
  log "L1-L6 ヘルスチェック開始"

  local ts
  ts=$(timestamp_utc)
  local next_check_ts
  next_check_ts=$(date -u -d "+5 minutes" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
    || python3 -c "import datetime; print((datetime.datetime.utcnow()+datetime.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))" 2>/dev/null \
    || echo "")

  log "L1: インフラチェック"
  local l1_json; l1_json=$(check_l1)
  local l1_status; l1_status=$(echo "${l1_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "FAIL")

  log "L2: スケジューラチェック"
  local l2_json; l2_json=$(check_l2)
  local l2_status; l2_status=$(echo "${l2_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "FAIL")

  log "L3: AI判定チェック"
  local l3_json; l3_json=$(check_l3)
  local l3_status; l3_status=$(echo "${l3_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "FAIL")

  log "L4: ユーザー反応チェック"
  local l4_json; l4_json=$(check_l4)
  local l4_status; l4_status=$(echo "${l4_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "FAIL")

  log "L5: 実取引チェック"
  local l5_json; l5_json=$(check_l5)
  local l5_status; l5_status=$(echo "${l5_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "FAIL")

  log "L6: 収益チェック"
  local l6_json; l6_json=$(check_l6)
  local l6_status; l6_status=$(echo "${l6_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "WARN")

  log "L7: ディスクチェック"
  local l7_json; l7_json=$(check_disk)
  local l7_status; l7_status=$(echo "${l7_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "WARN")

  log "L8 (Gate 8): Loki /ready チェック"
  local l8_json; l8_json=$(check_loki)
  local l8_status; l8_status=$(echo "${l8_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "FAIL")

  # L9: Proposal 発火レート異常検知 (P0-X2 / 2026-05-21)
  # psql 失敗時は WARN/skip を返し overall を壊さない。FAIL 時は overall FAIL に寄与。
  log "L9: Proposal 発火レートチェック"
  local l9_json; l9_json=$(check_proposal_rate)
  local l9_status; l9_status=$(echo "${l9_json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "WARN")

  # 全体判定
  # - L6 WARN は FAIL ではない (UAT期間中常態化)
  # - L7 CRITICAL → FAIL / L7 WARN は FAIL ではない
  # - L8 FAIL → FAIL (cascade 早期検知)
  # - L9 FAIL → FAIL (proposal 爆発的発火検知) / L9 WARN は非 fatal
  local overall_status="PASS"
  for s in "${l1_status}" "${l2_status}" "${l3_status}" "${l4_status}" "${l5_status}" "${l8_status}" "${l9_status}"; do
    if [[ "${s}" == "FAIL" ]]; then
      overall_status="FAIL"
      break
    fi
  done
  if [[ "${l7_status}" == "CRITICAL" ]]; then
    overall_status="FAIL"
  fi

  log "結果: L1=${l1_status} L2=${l2_status} L3=${l3_status} L4=${l4_status} L5=${l5_status} L6=${l6_status} L7=${l7_status} L8=${l8_status} L9=${l9_status} → ${overall_status}"

  # Slack 通知 JSON 組み立て
  local slack_json
  slack_json=$(python3 -c "
import json, sys

overall = '${overall_status}'
ts = '${ts}'
next_check = '${next_check_ts}'

l1 = json.loads('''${l1_json}''')
l2 = json.loads('''${l2_json}''')
l3 = json.loads('''${l3_json}''')
l4 = json.loads('''${l4_json}''')
l5 = json.loads('''${l5_json}''')
l6 = json.loads('''${l6_json}''')
l7 = json.loads('''${l7_json}''')
l8 = json.loads('''${l8_json}''')
l9 = json.loads('''${l9_json}''')

icon = '✅' if overall == 'PASS' else '🚨'
results = {
  'task': 'healthcheck_l1_l9',
  'status': overall,
  'timestamp': ts,
  'results': {
    'L1': l1,
    'L2': l2,
    'L3': l3,
    'L4': l4,
    'L5': l5,
    'L6': l6,
    'L7_disk': l7,
    'L8_loki': l8,
    'L9_proposal_rate': l9,
  },
  'next_check': next_check
}

text = f\"{icon} [healthcheck_l1_l6] {overall}\\n\"
for k, v in results['results'].items():
    text += f\"  {k}: {v['status']} — {json.dumps(v, ensure_ascii=False)}\\n\"

payload = {'text': text, 'attachments': [{'color': '#36a64f' if overall == 'PASS' else '#ff0000', 'text': json.dumps(results, ensure_ascii=False, indent=2)}]}
print(json.dumps(payload))
" 2>/dev/null || python3 -c "
import json
payload = {'text': '[healthcheck_l1_l6] ${overall_status} — JSON build error, check logs'}
print(json.dumps(payload))
")

  # 通知ポリシー適用
  if [[ "${overall_status}" == "PASS" ]]; then
    if should_send_pass_notification; then
      log "PASS 通知送信 (1時間ぶり)"
      send_slack "${slack_json}"
      record_pass_time
    else
      log "PASS 通知スキップ (冷却期間中)"
    fi
  else
    # FAIL: dedup/throttle 付き送信 (アラート疲労対策)
    local fail_count
    fail_count=$(increment_fail_count)

    # failed_layers シグネチャを先に算出 (throttle 判定と Twilio 双方で使う)
    local failed_layers=""
    [[ "${l1_status}" == "FAIL" ]] && failed_layers="${failed_layers}L1 "
    [[ "${l2_status}" == "FAIL" ]] && failed_layers="${failed_layers}L2 "
    [[ "${l3_status}" == "FAIL" ]] && failed_layers="${failed_layers}L3 "
    [[ "${l4_status}" == "FAIL" ]] && failed_layers="${failed_layers}L4 "
    [[ "${l5_status}" == "FAIL" ]] && failed_layers="${failed_layers}L5 "
    [[ "${l7_status}" == "CRITICAL" ]] && failed_layers="${failed_layers}L7(disk) "
    [[ "${l8_status}" == "FAIL" ]] && failed_layers="${failed_layers}L8(loki) "
    [[ "${l9_status}" == "FAIL" ]] && failed_layers="${failed_layers}L9(proposal_rate) "
    failed_layers="${failed_layers:-L1-L5}"

    # 状態変化時は即送信 / 同一FAIL継続中は FAIL_RESEND_COOLDOWN_SEC に1回だけ再送
    if should_send_fail_notification "${failed_layers}"; then
      log "FAIL 通知送信 (連続 ${fail_count} 回目, layers=${failed_layers})"
      send_slack "${slack_json}"
    else
      log "FAIL 通知抑止 (同一FAIL継続: ${failed_layers}, 連続 ${fail_count} 回目, 再送間隔 ${FAIL_RESEND_COOLDOWN_SEC}s 未満)"
    fi

    # 5連続FAIL → Twilio 電話エスカレーション (throttle とは独立に評価。
    # 第2の砦なので埋没対策の対象外=連続FAILが続く限りレート制限内で発火させる)
    # L6 単独 FAIL は対象外 (overall_status が FAIL になるのは L1-L5 の FAIL のみ)
    if [[ "${fail_count}" -ge "${TWILIO_CONSECUTIVE_FAIL_THRESHOLD}" ]]; then
      log "5連続FAIL到達 (${fail_count}回) — Twilio 電話エスカレーション発動: ${failed_layers}"
      call_twilio_phone "${fail_count}" "${failed_layers}"
    fi
  fi

  # DRY_RUN でない場合のみ stdout に出力 (DRY_RUN は send_slack 内で出力済み)
  if [[ "${DRY_RUN}" != "true" ]]; then
    echo "${slack_json}" | python3 -m json.tool 2>/dev/null || echo "${slack_json}"
  fi

  if [[ "${overall_status}" == "PASS" ]]; then
    return 0
  else
    return 1
  fi
}

main "$@"
