#!/usr/bin/env bash
# uata-stuck-detector.sh — Claude Code session stuck detection + Slack alert
#
# 背景: Claude Code の [Tool result missing due to internal error] バグ
#   (GitHub issues #43866, #44068, #39830, #46767) により 24h 自走中に
#   session が無応答になることがある。本スクリプトで検知して Slack 通知する。
#
# 仕組み:
#   1. PostToolUse hook (update-heartbeat.sh) が各 tool 実行後に /tmp/uata-heartbeat に書込み
#   2. 本スクリプト (daemon) が 5 分ごとに heartbeat の更新時刻を確認
#   3. 30 分間更新なし → STUCK-DETECTED を Slack #ultra-auto-project に送信
#
# 使い方:
#   ./scripts/uata-stuck-detector.sh start   — バックグラウンドで監視開始
#   ./scripts/uata-stuck-detector.sh stop    — 監視停止
#   ./scripts/uata-stuck-detector.sh status  — 現在の状態表示
#   ./scripts/uata-stuck-detector.sh test    — 模擬 stuck で Slack 通知テスト
#
# 環境変数:
#   STUCK_THRESHOLD_MIN  — 無応答判定時間 (分、デフォルト 30)
#   CHECK_INTERVAL_SEC   — チェック間隔 (秒、デフォルト 300 = 5分)
#   SLACK_WEBHOOK_URL    — Webhook URL (未設定時は .env.production / SSH fallback)
#   DRY_RUN              — 1 のとき Slack 送信をスキップ (dry-run テスト用)

set -euo pipefail

# ── 設定 ─────────────────────────────────────────────────────────────────
STUCK_THRESHOLD_MIN="${STUCK_THRESHOLD_MIN:-30}"
CHECK_INTERVAL_SEC="${CHECK_INTERVAL_SEC:-300}"
HEARTBEAT_FILE="${HEARTBEAT_FILE:-/tmp/uata-heartbeat}"
PID_FILE="/tmp/uata-stuck-detector.pid"
LOG_FILE="/tmp/uata-stuck-detector.log"
SESSION_LOG_DIR="${HOME}/.claude-uata/projects/-opt-ultra-autotrade-main"
GIT_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo "")"

# ── Webhook 取得 ──────────────────────────────────────────────────────────
get_webhook() {
  # 1. 環境変数
  if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "$SLACK_WEBHOOK_URL"
    return
  fi
  # 2. ~/.config/uata/slack-webhook (dev VPS 用ローカル設定ファイル)
  if [[ -f "${HOME}/.config/uata/slack-webhook" ]]; then
    cat "${HOME}/.config/uata/slack-webhook"
    return
  fi
  # 3. git root の .env.production (本番VPS / ローカルMac)
  if [[ -n "$GIT_ROOT" && -f "${GIT_ROOT}/.env.production" ]]; then
    grep "^SLACK_WEBHOOK_URL=" "${GIT_ROOT}/.env.production" | head -1 | cut -d= -f2-
    return
  fi
  # 4. SSH fallback (Hetzner本番VPS — dev VPS からは接続不可の場合あり)
  local ssh_key="${HOME}/.ssh/hetzner_direct"
  if [[ -f "$ssh_key" ]]; then
    ssh -i "$ssh_key" \
      -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes \
      ultra@77.42.46.155 \
      'grep SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | head -1 | cut -d= -f2-' \
      2>/dev/null || echo ""
  else
    echo ""
  fi
}

send_slack() {
  local message="$1"
  local webhook="$2"
  if [[ -z "$webhook" ]]; then
    echo "[send_slack] WARNING: webhook URL が空、Slack 送信をスキップ" >&2
    return 0
  fi
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "[DRY_RUN] Slack 送信スキップ: ${message:0:100}" >&2
    return 0
  fi
  curl -sS -X POST "$webhook" \
    -H "Content-Type: application/json" \
    --data-raw "{\"text\": \"${message}\"}" \
    --max-time 10 >/dev/null 2>&1 || {
    echo "[send_slack] WARNING: curl 失敗 (非致命的)" >&2
  }
}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

# ── heartbeat 確認 ──────────────────────────────────────────────────────────
get_heartbeat_age_min() {
  # 1. heartbeat ファイルがあればそれを使用
  if [[ -f "$HEARTBEAT_FILE" ]]; then
    local last_mod
    last_mod=$(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || echo 0)
    echo $(( ($(date +%s) - last_mod) / 60 ))
    return
  fi
  # 2. fallback: session log (.jsonl) の最終更新時刻
  local latest_log
  latest_log=$(find "$SESSION_LOG_DIR" -name "*.jsonl" -type f 2>/dev/null \
    | xargs ls -t 2>/dev/null | head -1)
  if [[ -n "$latest_log" ]]; then
    local last_mod
    last_mod=$(stat -c %Y "$latest_log" 2>/dev/null || echo 0)
    echo $(( ($(date +%s) - last_mod) / 60 ))
    return
  fi
  # 3. heartbeat もセッションログもない → 監視不可
  echo -1
}

# ── メイン監視ループ ──────────────────────────────────────────────────────
monitor_loop() {
  local webhook
  webhook=$(get_webhook)
  if [[ -z "$webhook" ]]; then
    log "ERROR: SLACK_WEBHOOK_URL が取得できません。Slack 通知は無効化されます。"
  fi

  log "Stuck detector 開始 (threshold=${STUCK_THRESHOLD_MIN}min, interval=${CHECK_INTERVAL_SEC}s)"
  log "heartbeat_file=${HEARTBEAT_FILE} session_log_dir=${SESSION_LOG_DIR}"

  local last_alerted_at=0

  while true; do
    sleep "$CHECK_INTERVAL_SEC"

    local age_min
    age_min=$(get_heartbeat_age_min)

    if [[ "$age_min" -eq -1 ]]; then
      log "INFO: heartbeat / session log なし。監視スキップ。"
      continue
    fi

    log "heartbeat_age=${age_min}min (threshold=${STUCK_THRESHOLD_MIN}min)"

    if [[ "$age_min" -ge "$STUCK_THRESHOLD_MIN" ]]; then
      local now
      now=$(date +%s)
      # 30分以内に同じ stuck で重複アラートを出さない
      if (( now - last_alerted_at > 1800 )); then
        local claude_pid
        claude_pid=$(pgrep -x claude 2>/dev/null | head -1 || echo "不明")
        local git_branch
        git_branch=$(git -C "${GIT_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "不明")

        local msg
        msg="🚨 *STUCK-DETECTED* \`uata-stuck-detector\`\\n"
        msg+="最終 tool 実行から *${age_min}分* 経過 (閾値: ${STUCK_THRESHOLD_MIN}分)\\n"
        msg+="Claude PID: \`${claude_pid}\`  ブランチ: \`${git_branch}\`\\n"
        msg+="対処: ターミナルで \`claude --resume\` を実行してセッションを再開\\n"
        msg+="ログ: \`tail -20 ${LOG_FILE}\`"

        send_slack "$msg" "$webhook"
        log "STUCK-ALERT 送信 (age=${age_min}min, pid=${claude_pid})"
        last_alerted_at=$now
      else
        log "STUCK 継続中 (age=${age_min}min) — 重複アラート抑制"
      fi
    else
      last_alerted_at=0
    fi
  done
}

# ── サブコマンド ──────────────────────────────────────────────────────────
cmd="${1:-help}"

case "$cmd" in
  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "stuck-detector は既に起動中 (PID=$(cat "$PID_FILE"))"
      exit 0
    fi
    monitor_loop &
    echo $! > "$PID_FILE"
    echo "stuck-detector 起動 (PID=$!, log=${LOG_FILE})"
    ;;

  stop)
    if [[ -f "$PID_FILE" ]]; then
      local_pid=$(cat "$PID_FILE")
      kill "$local_pid" 2>/dev/null && echo "stuck-detector 停止 (PID=${local_pid})" || echo "PID=${local_pid} は既に終了"
      rm -f "$PID_FILE"
    else
      echo "stuck-detector は起動していません"
    fi
    ;;

  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      local_pid=$(cat "$PID_FILE")
      age_min=$(get_heartbeat_age_min)
      echo "状態: 稼働中 (PID=${local_pid})"
      echo "heartbeat_age: ${age_min}min / 閾値: ${STUCK_THRESHOLD_MIN}min"
      echo "最新ログ:"
      tail -5 "$LOG_FILE" 2>/dev/null || echo "(ログなし)"
    else
      echo "状態: 停止"
    fi
    ;;

  test)
    echo "=== dry-run テスト: STUCK 模擬 Slack 通知 ==="
    webhook=$(get_webhook)
    if [[ -z "$webhook" ]]; then
      echo "ERROR: webhook URL が取得できません"
      exit 1
    fi
    test_msg="🧪 *[TEST] STUCK-DETECTED 模擬通知* \`uata-stuck-detector dry-run\`\\n"
    test_msg+="これは dry-run テスト送信です。本番 stuck 検知ではありません。\\n"
    test_msg+="threshold=${STUCK_THRESHOLD_MIN}min / interval=${CHECK_INTERVAL_SEC}s"

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      echo "[DRY_RUN] 送信予定メッセージ:"
      echo "$test_msg"
    else
      send_slack "$test_msg" "$webhook"
      echo "Slack 送信完了 (#ultra-auto-project)"
    fi
    ;;

  help|*)
    echo "使い方: $0 {start|stop|status|test}"
    echo ""
    echo "  start   バックグラウンドで監視開始"
    echo "  stop    監視停止"
    echo "  status  現在の状態表示"
    echo "  test    模擬 stuck で Slack 通知テスト"
    echo ""
    echo "環境変数:"
    echo "  STUCK_THRESHOLD_MIN  無応答判定時間 (分、デフォルト 30)"
    echo "  CHECK_INTERVAL_SEC   チェック間隔 (秒、デフォルト 300)"
    echo "  DRY_RUN=1            Slack 送信スキップ (テスト用)"
    ;;
esac
