#!/usr/bin/env bash
# scripts/staging_observation_monitor.sh
#
# Stream 8: staging #365 観測進捗 + UAT 動線監視スクリプト
#
# 目的:
#   - 2026-05-21 P0 (scheduler 暴走 / proposal spike) の再発検知
#   - #365 PR (SELL/BUY dual-agent AND 条件) 効果観測: staging ai_decisions を集計して Slack 通知
#   - staging / production health の定期確認
#
# ============================================================
# cron 登録手順 (本番 VPS / ultra ユーザー)
# ============================================================
# 1. crontab 編集:
#      crontab -e  (ultra ユーザー)
#
# 2. 推奨 cron 設定 (4時間ごと観測レポート):
#      0 */4 * * * /opt/ultra-autotrade/scripts/staging_observation_monitor.sh >> /opt/ultra-autotrade/logs/staging_obs_monitor.log 2>&1
#
# 3. 5分ごとの spike/health 警戒モード (UAT 期間中のみ推奨):
#      */5 * * * * WINDOW="1 hour" /opt/ultra-autotrade/scripts/staging_observation_monitor.sh >> /opt/ultra-autotrade/logs/staging_obs_monitor.log 2>&1
#
# 4. ログディレクトリ作成:
#      mkdir -p /opt/ultra-autotrade/logs
#
# ============================================================
# env override 一覧
# ============================================================
#   ENV_FILE                     .env.production パス
#                                (default: /opt/ultra-autotrade/.env.production)
#   SLACK_WEBHOOK_URL            Slack Webhook URL
#                                (未設定時は ENV_FILE から SLACK_WEBHOOK_URL= を抽出)
#   STAGING_POSTGRES_CONTAINER   staging postgres コンテナ名
#                                (default: ultra-autotrade-postgres-staging-new)
#   STAGING_DB_USER              staging postgres ユーザー (default: ultra)
#   STAGING_DB_NAME              staging postgres DB 名
#                                (default: ultra_autotrade_staging)
#   STAGING_HEALTH_URL           staging health endpoint
#                                (default: http://127.0.0.1:8082/health)
#   PRODUCTION_HEALTH_URL        production health endpoint
#                                (default: http://127.0.0.1:8000/health)
#   WINDOW                       観測ウィンドウ (PostgreSQL INTERVAL 文字列)
#                                (default: "4 hours")
#   PROPOSAL_SPIKE_THRESHOLD     直近1時間の proposals 件数異常閾値
#                                (default: 20)
#   BUY_SELL_ALERT_WINDOW        BUY+SELL=0 チェックのウィンドウ (default: "8 hours")
#   DRY_RUN                      true の場合 Slack 通知を stdout 出力のみに変更
#                                (default: false)
#   CURL_TIMEOUT                 curl タイムアウト秒 (default: 10)
#
# ============================================================
# dev VPS での動作 (DRY_RUN 相当)
# ============================================================
#   dev VPS は本番 DB / staging DB に接続できないため、
#   psql 実行が失敗した場合はスキップしてログに記録する。
#   health curl も接続先がないため WARN として skip する。
#   ---> script 全体は exit 0 で終了し、cron を壊さない。
#
# ============================================================

set -uo pipefail

SCRIPT_NAME="staging_observation_monitor"

# --- 環境変数デフォルト ---
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"
STAGING_POSTGRES_CONTAINER="${STAGING_POSTGRES_CONTAINER:-ultra-autotrade-postgres-staging-new}"
STAGING_DB_USER="${STAGING_DB_USER:-ultra}"
STAGING_DB_NAME="${STAGING_DB_NAME:-ultra_autotrade_staging}"
STAGING_HEALTH_URL="${STAGING_HEALTH_URL:-http://127.0.0.1:8082/health}"
PRODUCTION_HEALTH_URL="${PRODUCTION_HEALTH_URL:-http://127.0.0.1:8000/health}"
WINDOW="${WINDOW:-4 hours}"
PROPOSAL_SPIKE_THRESHOLD="${PROPOSAL_SPIKE_THRESHOLD:-20}"
BUY_SELL_ALERT_WINDOW="${BUY_SELL_ALERT_WINDOW:-8 hours}"
DRY_RUN="${DRY_RUN:-false}"
CURL_TIMEOUT="${CURL_TIMEOUT:-10}"

# --- Slack Webhook 解決 ---
if [[ -z "${SLACK_WEBHOOK_URL:-}" ]] && [[ -f "${ENV_FILE}" ]]; then
  SLACK_WEBHOOK_URL=$(grep "^SLACK_WEBHOOK_URL=" "${ENV_FILE}" | cut -d= -f2- | tr -d '"' || true)
fi
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

# --- ユーティリティ ---
timestamp_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  echo "$(timestamp_utc) [${SCRIPT_NAME}] $*"
}

# Slack 通知 (DRY_RUN=true の場合は stdout のみ)
notify_slack() {
  local msg="$1"
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY_RUN] Slack通知 (送信スキップ): ${msg}"
    return 0
  fi
  if [[ -z "${SLACK_WEBHOOK_URL}" ]]; then
    log "WARN: SLACK_WEBHOOK_URL 未設定 — 通知スキップ: ${msg}"
    return 0
  fi
  curl -sf -X POST "${SLACK_WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"${msg}\"}" >/dev/null 2>&1 \
    || log "WARN: Slack 通知送信失敗 (webhook curl error)"
}

# psql をコンテナ経由で実行し、結果を返す
# 失敗時は空文字を返し (exit 0)、呼び出し側でスキップ判断
psql_query() {
  local sql="$1"
  docker exec "${STAGING_POSTGRES_CONTAINER}" \
    psql -U "${STAGING_DB_USER}" -d "${STAGING_DB_NAME}" \
    -t -A -F',' -c "${sql}" 2>/dev/null \
    || true
}

# =============================================================================
# チェック 1: staging / production health
# =============================================================================
check_health() {
  log "--- [health] staging / production health チェック ---"
  local alerts=""

  # staging health
  local staging_code
  staging_code=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout "${CURL_TIMEOUT}" --max-time "${CURL_TIMEOUT}" \
    "${STAGING_HEALTH_URL}" 2>/dev/null; echo "")
  staging_code=$(echo "${staging_code}" | tr -d '[:space:]' | tail -c 3)
  staging_code="${staging_code:-000}"
  log "staging health: ${staging_code}"

  if [[ "${staging_code}" != "200" ]]; then
    alerts="${alerts}🚨 staging health=${staging_code} (${STAGING_HEALTH_URL})\n"
  fi

  # production health
  local prod_code
  prod_code=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout "${CURL_TIMEOUT}" --max-time "${CURL_TIMEOUT}" \
    "${PRODUCTION_HEALTH_URL}" 2>/dev/null; echo "")
  prod_code=$(echo "${prod_code}" | tr -d '[:space:]' | tail -c 3)
  prod_code="${prod_code:-000}"
  log "production health: ${prod_code}"

  if [[ "${prod_code}" != "200" ]]; then
    alerts="${alerts}🚨 production health=${prod_code} (${PRODUCTION_HEALTH_URL})\n"
  fi

  if [[ -n "${alerts}" ]]; then
    notify_slack "$(printf '%b' "${alerts}")"
  else
    log "[health] staging=${staging_code}, production=${prod_code} — OK"
  fi
}

# =============================================================================
# チェック 2: staging ai_decisions 観測レポート (#365 効果観測)
# =============================================================================
check_ai_decisions() {
  log "--- [ai_decisions] 観測ウィンドウ: ${WINDOW} ---"

  # ai_decisions テーブル存在確認
  local table_exists
  table_exists=$(psql_query "SELECT to_regclass('public.ai_decisions') IS NOT NULL;" | head -1)
  if [[ "${table_exists}" != "t" ]]; then
    log "SKIP: ai_decisions テーブル未確認 (dev VPS / psql 失敗 / テーブル未存在)"
    return 0
  fi

  # BUY/SELL/HOLD 件数を prompt_version 別に集計
  local result
  result=$(psql_query \
    "SELECT action, COALESCE(prompt_version, 'unknown') as pv, COUNT(*) \
     FROM ai_decisions \
     WHERE created_at > NOW() - INTERVAL '${WINDOW}' \
     GROUP BY action, pv \
     ORDER BY action, pv;" 2>/dev/null || true)

  if [[ -z "${result}" ]]; then
    log "SKIP: ai_decisions クエリ結果なし (DB 接続失敗または0件)"
    return 0
  fi

  log "ai_decisions 集計結果 (${WINDOW}):"
  log "${result}"

  # 集計値を解析
  local buy_count=0 sell_count=0 hold_count=0
  while IFS=',' read -r action pv cnt; do
    action=$(echo "${action}" | tr -d '[:space:]')
    cnt=$(echo "${cnt}" | tr -d '[:space:]')
    case "${action}" in
      BUY)  buy_count=$((buy_count + cnt)) ;;
      SELL) sell_count=$((sell_count + cnt)) ;;
      HOLD) hold_count=$((hold_count + cnt)) ;;
    esac
  done <<< "${result}"

  local total=$((buy_count + sell_count + hold_count))
  local hold_rate="N/A"
  if [[ "${total}" -gt 0 ]]; then
    hold_rate=$(python3 -c "print(f'{${hold_count}/${total}*100:.1f}')" 2>/dev/null || echo "N/A")
  fi

  local msg
  msg="📊 [staging obs / #365] ai_decisions レポート (直近 ${WINDOW})\n"
  msg="${msg}  BUY: ${buy_count} / SELL: ${sell_count} / HOLD: ${hold_count} (total: ${total})\n"
  msg="${msg}  HOLD率: ${hold_rate}%\n"
  msg="${msg}  観測バックエンド: ${STAGING_POSTGRES_CONTAINER}"

  notify_slack "$(printf '%b' "${msg}")"

  # --- 異常アラート: BUY+SELL=0 ---
  # 直近 BUY_SELL_ALERT_WINDOW で trade 判定が一切ない場合
  # NOTE: WINDOW と BUY_SELL_ALERT_WINDOW は独立。WINDOW=4h でも 8h チェックを追加実施。
  local bs_window_count
  bs_window_count=$(psql_query \
    "SELECT COUNT(*) FROM ai_decisions \
     WHERE created_at > NOW() - INTERVAL '${BUY_SELL_ALERT_WINDOW}' \
     AND action IN ('BUY', 'SELL');" | head -1 | tr -d '[:space:]')
  bs_window_count="${bs_window_count:-0}"

  if [[ "${bs_window_count}" == "0" || "${bs_window_count}" == "" ]]; then
    notify_slack "$(printf '⚠️ [staging obs / #365] 直近 %s で BUY+SELL=0。\nAND 条件が厳しすぎる候補 — #365 閾値 65%% 再調整検討。\nHOLD 連続の場合はログを確認してください。' "${BUY_SELL_ALERT_WINDOW}")"
    log "ALERT: BUY+SELL=0 (${BUY_SELL_ALERT_WINDOW})"
  else
    log "[ai_decisions] 直近 ${BUY_SELL_ALERT_WINDOW} の BUY+SELL=${bs_window_count} — OK"
  fi
}

# =============================================================================
# チェック 3: proposal spike 検知 (P0 再発防止 / 直近 1h)
# =============================================================================
check_proposal_spike() {
  log "--- [proposal_spike] 直近 1h の proposals 件数チェック ---"

  # proposals テーブル存在確認
  local table_exists
  table_exists=$(psql_query "SELECT to_regclass('public.proposals') IS NOT NULL;" | head -1)
  if [[ "${table_exists}" != "t" ]]; then
    log "SKIP: proposals テーブル未確認 (dev VPS / psql 失敗 / テーブル未存在)"
    return 0
  fi

  local count
  count=$(psql_query \
    "SELECT COUNT(*) FROM proposals \
     WHERE created_at > NOW() - INTERVAL '1 hour';" | head -1 | tr -d '[:space:]')
  count="${count:-0}"

  log "proposals (直近1h): ${count} 件 (threshold: ${PROPOSAL_SPIKE_THRESHOLD})"

  if [[ "${count}" -gt "${PROPOSAL_SPIKE_THRESHOLD}" ]]; then
    notify_slack "$(printf '🚨 [staging obs] proposal spike 検知！\n直近 1h: %s 件 > 閾値 %s 件\nP0 再発 (scheduler 暴走) の疑い。直ちに確認してください。\nコンテナ: %s' \
      "${count}" "${PROPOSAL_SPIKE_THRESHOLD}" "${STAGING_POSTGRES_CONTAINER}")"
    log "ALERT: proposal spike count=${count}"
  else
    log "[proposal_spike] count=${count} — 正常範囲"
  fi
}

# =============================================================================
# メイン
# =============================================================================
main() {
  log "=== ${SCRIPT_NAME} 開始 (DRY_RUN=${DRY_RUN}) ==="
  log "WINDOW=${WINDOW}, PROPOSAL_SPIKE_THRESHOLD=${PROPOSAL_SPIKE_THRESHOLD}"
  log "STAGING_HEALTH_URL=${STAGING_HEALTH_URL}"
  log "PRODUCTION_HEALTH_URL=${PRODUCTION_HEALTH_URL}"
  log "STAGING_POSTGRES_CONTAINER=${STAGING_POSTGRES_CONTAINER}"

  check_health
  check_ai_decisions
  check_proposal_spike

  log "=== ${SCRIPT_NAME} 完了 ==="
}

main "$@"
