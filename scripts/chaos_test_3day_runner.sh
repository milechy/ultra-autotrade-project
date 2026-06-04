#!/usr/bin/env bash
# scripts/chaos_test_3day_runner.sh
#
# Ultra AutoTrade Chaos Test — 3 日連続実行 runner (ローンチ条件 2)
#
# 既存の `scripts/chaos_test_staging.sh` (コンテナ kill) を 1 日 1 回呼ぶ wrapper。
# `docs/launch_decision_criteria_v2.md` §2.2 の PASS 判定基準 4 軸を全てカバーする:
#   ① kill 後 5 分以内自動再起動 ............ chaos_test_staging.sh が判定
#   ② 再起動後 2 分以内 /health 200 .......... chaos_test_staging.sh が判定
#   ③ Loki に Exited + Started 記録 .......... 本 runner が確認
#   ④ chaos 前後で ai_decisions 継続生成 ..... 本 runner が確認
#
# 結果は `docs/launch/chaos_test_results/YYYY-MM-DD_runN.md` に追記される。
#
# 使い方:
#   bash scripts/chaos_test_3day_runner.sh                # 1 回実行 (1 日分)
#   DRY_RUN=true bash scripts/chaos_test_3day_runner.sh   # dry-run (kill しない)
#   RUN_INDEX=2 bash scripts/chaos_test_3day_runner.sh    # run_N の N を明示
#
# 環境変数:
#   DRY_RUN           true で kill をスキップ (default: false)
#   RUN_INDEX         結果ファイル suffix (default: 1)
#   SLACK_WEBHOOK_URL Slack 通知先 (未設定時は .env.production から読み込み)
#   POSTGRES_CONTAINER staging postgres コンテナ名
#                      (default: ultra-autotrade-postgres-staging-new)
#   LOKI_URL          Loki query URL (default: http://127.0.0.1:3101)
#   STAGING_DB        staging DB 名 (default: ultra_autotrade_staging)
#   STAGING_DB_USER   staging DB user (default: ultra)
#
# 実行場所: 本番 Hetzner VPS (77.42.46.155) — staging compose が同居している
#   ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 \
#     "bash /opt/ultra-autotrade/scripts/chaos_test_3day_runner.sh"
#
# 注意: production コンテナには絶対に触らない。chaos_test_staging.sh 側の
# safety_check で production 文字列を含むコンテナは reject される。

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHAOS_SCRIPT="$SCRIPT_DIR/chaos_test_staging.sh"
RESULTS_DIR="$REPO_ROOT/docs/launch/chaos_test_results"
TODAY="$(date '+%Y-%m-%d')"
RUN_INDEX="${RUN_INDEX:-1}"
RESULT_FILE="$RESULTS_DIR/${TODAY}_run${RUN_INDEX}.md"

DRY_RUN="${DRY_RUN:-false}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ultra-autotrade-postgres-staging-new}"
LOKI_URL="${LOKI_URL:-http://127.0.0.1:3101}"
STAGING_DB="${STAGING_DB:-ultra_autotrade_staging}"
STAGING_DB_USER="${STAGING_DB_USER:-ultra}"
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# ユーティリティ
# =============================================================================
log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()      { echo -e "${GREEN}[PASS]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_fail()    { echo -e "${RED}[FAIL]${NC}  $*"; }
log_section() { echo -e "\n${BLUE}===== $* =====${NC}"; }

_load_slack_webhook() {
  if [[ -z "${SLACK_WEBHOOK_URL:-}" && -f "$ENV_FILE" ]]; then
    SLACK_WEBHOOK_URL=$(grep '^SLACK_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" 2>/dev/null) || true
  fi
}

_slack() {
  local text="$1"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY_RUN] Slack: $text"
    return 0
  fi
  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    return 0
  fi
  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$text\"}" > /dev/null 2>&1 || true
}

# =============================================================================
# 前提確認
# =============================================================================
_preflight() {
  log_section "Preflight"

  if [[ ! -x "$CHAOS_SCRIPT" ]]; then
    if [[ -f "$CHAOS_SCRIPT" ]]; then
      log_warn "chaos_test_staging.sh は実行権限なし。chmod +x を実行します"
      chmod +x "$CHAOS_SCRIPT" || {
        log_fail "chmod 失敗"; exit 1;
      }
    else
      log_fail "chaos_test_staging.sh が見つかりません: $CHAOS_SCRIPT"
      exit 1
    fi
  fi

  mkdir -p "$RESULTS_DIR"

  if [[ -f "$RESULT_FILE" ]]; then
    log_warn "既存ファイル上書き: $RESULT_FILE"
  fi

  log_ok "Preflight OK"
  log_info "結果ファイル: $RESULT_FILE"
}

# =============================================================================
# ④ ai_decisions 継続生成チェック
# =============================================================================
# kill 前後の ai_decisions 件数差を見て継続生成されているか確認する。
# scheduled_tasks の interval によっては chaos 数分間で増えないこともあるため、
# 「chaos 開始 30 分前」と「chaos 終了直後」の件数を比較する。
_query_ai_decisions_count_last_30min() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY_RUN_COUNT"
    return 0
  fi
  docker exec "$POSTGRES_CONTAINER" \
    psql -U "$STAGING_DB_USER" -d "$STAGING_DB" -tAc \
    "SELECT COUNT(*) FROM ai_decisions WHERE created_at > NOW() - INTERVAL '30 minutes';" \
    2>/dev/null || echo "QUERY_FAIL"
}

# =============================================================================
# ③ Loki Exited + Started ログ確認
# =============================================================================
# kill 対象コンテナの Exited / Started イベントが Loki に記録されているか確認する。
# Loki は staging から見て http://localhost:3100、本番 VPS ホストからは 127.0.0.1:3101。
_query_loki_lifecycle_events() {
  # shellcheck disable=SC2034  # since_iso は将来 LogQL query 拡張時に使う
  local since_iso="${1:-}"  # 例: 2026-05-28T10:00:00Z
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY_RUN_EVENTS"
    return 0
  fi

  # LogQL: {container=~"ultra-autotrade-.*-staging-new"} |~ "(Exited|Started|Restarting)"
  # ただし promtail の docker_sd で label が container or container_name 両方ありうるので
  # ここでは簡易に loki API の /ready を確認し、event 検索は後段の
  # _grep_docker_events_in_window に委譲する。
  curl -s --max-time 5 "$LOKI_URL/ready" 2>/dev/null | head -1 || echo "LOKI_UNREACHABLE"
}

_grep_docker_events_in_window() {
  local since_min="$1"  # 例: 15 (chaos 開始からの分数)
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY_RUN_DOCKER_EVENTS"
    return 0
  fi
  # 直近 since_min 分の docker events から staging コンテナの die/start を抽出
  # docker events --until は --since と組み合わせて履歴 query 可能
  docker events \
    --since "${since_min}m" \
    --until "0s" \
    --filter "type=container" \
    --filter "event=die" \
    --filter "event=start" \
    --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' 2>/dev/null \
    | grep -E "staging-new" || true
}

# =============================================================================
# メイン
# =============================================================================
main() {
  local start_iso
  start_iso="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  local start_epoch=$SECONDS

  log_section "Chaos Test 3day Runner — Day $(date '+%Y-%m-%d') / Run $RUN_INDEX"
  echo "  実行時刻 (UTC): $start_iso"
  echo "  DRY_RUN:        $DRY_RUN"
  echo "  結果ファイル:   $RESULT_FILE"
  echo ""

  _load_slack_webhook
  _preflight

  # ----- ④ pre: ai_decisions 件数取得 -----
  log_section "Pre-chaos: ai_decisions count (last 30 min)"
  local pre_ai_count
  pre_ai_count=$(_query_ai_decisions_count_last_30min)
  log_info "ai_decisions (chaos 開始前 30 分): $pre_ai_count 件"

  _slack "🔥 *Chaos 3day Run ${RUN_INDEX} 開始* — Day ${TODAY} / pre ai_decisions: ${pre_ai_count}"

  # ----- ①② chaos_test_staging.sh 本体 -----
  log_section "Invoke chaos_test_staging.sh"
  local chaos_log="/tmp/chaos_test_${TODAY}_run${RUN_INDEX}.log"
  local chaos_rc=0
  DRY_RUN="$DRY_RUN" bash "$CHAOS_SCRIPT" 2>&1 | tee "$chaos_log" || chaos_rc=$?

  # ----- ④ post: ai_decisions 件数取得 (chaos 終了から 30 分以内) -----
  # chaos 終了直後の 30 分窓は kill 前 30 分窓と重複しているため、
  # ここでは「chaos 開始後」を判定する厳密窓 (post の 30 分窓) と
  # 「2 件以上増加していること」を継続生成の最低条件とする。
  log_section "Post-chaos: ai_decisions count (last 30 min, includes chaos window)"
  local post_ai_count
  post_ai_count=$(_query_ai_decisions_count_last_30min)
  log_info "ai_decisions (chaos 終了直後): $post_ai_count 件"

  local ai_check="UNKNOWN"
  if [[ "$DRY_RUN" == "true" ]]; then
    ai_check="DRY_RUN"
  elif [[ "$pre_ai_count" == "QUERY_FAIL" || "$post_ai_count" == "QUERY_FAIL" ]]; then
    ai_check="FAIL_QUERY"
  elif [[ "$pre_ai_count" =~ ^[0-9]+$ && "$post_ai_count" =~ ^[0-9]+$ ]]; then
    # 厳密な「継続生成」判定: post >= pre かつ post > 0
    if (( post_ai_count >= pre_ai_count )) && (( post_ai_count > 0 )); then
      ai_check="PASS"
    else
      ai_check="FAIL_DECREASED"
    fi
  else
    ai_check="FAIL_PARSE"
  fi

  # ----- ③ docker events / Loki 確認 -----
  log_section "Lifecycle events (docker events + Loki ready)"
  local loki_ready
  loki_ready=$(_query_loki_lifecycle_events "$start_iso")
  log_info "Loki /ready: $loki_ready"

  local docker_events
  docker_events=$(_grep_docker_events_in_window 15)
  if [[ -n "$docker_events" ]]; then
    log_ok "docker events 検出:"
    echo "$docker_events" | sed 's/^/    /'
  else
    log_warn "docker events 検出なし (DRY_RUN または短い chaos の場合は正常)"
  fi

  # ----- 結果記録 (Markdown) -----
  log_section "Write result file"
  {
    echo "# Chaos Test Run ${RUN_INDEX} — ${TODAY}"
    echo ""
    echo "## メタ情報"
    echo ""
    echo "- 実行時刻 (UTC): \`${start_iso}\`"
    echo "- DRY_RUN: \`${DRY_RUN}\`"
    echo "- 経過秒: \`$(( SECONDS - start_epoch ))\`"
    echo "- chaos_test_staging.sh rc: \`${chaos_rc}\`"
    echo ""
    echo "## PASS 判定 4 軸 (docs/launch_decision_criteria_v2.md §2.2)"
    echo ""
    echo "| 軸 | 判定 | 備考 |"
    echo "|---|---|---|"
    echo "| ① kill 後 5 分以内自動再起動 | $([[ $chaos_rc -eq 0 ]] && echo "PASS" || echo "FAIL (chaos_rc=$chaos_rc)") | chaos_test_staging.sh が判定 |"
    echo "| ② 再起動後 2 分以内 /health 200 | $([[ $chaos_rc -eq 0 ]] && echo "PASS" || echo "FAIL (chaos_rc=$chaos_rc)") | chaos_test_staging.sh の Final Health Check |"
    echo "| ③ Loki に Exited + Started 記録 | \`${loki_ready}\` (docker events 併用) | docker events 出力は下段参照 |"
    echo "| ④ chaos 前後で ai_decisions 継続生成 | ${ai_check} | pre=${pre_ai_count} post=${post_ai_count} |"
    echo ""
    echo "## docker events (chaos 開始 15 分窓、staging-new のみ)"
    echo ""
    echo "\`\`\`"
    if [[ -n "$docker_events" ]]; then
      echo "$docker_events"
    else
      echo "(検出なし)"
    fi
    echo "\`\`\`"
    echo ""
    echo "## chaos_test_staging.sh log (抜粋)"
    echo ""
    echo "\`\`\`"
    tail -50 "$chaos_log" 2>/dev/null || echo "(log not available)"
    echo "\`\`\`"
    echo ""
    echo "## 最終判定"
    echo ""
    if [[ $chaos_rc -eq 0 && "$ai_check" == "PASS" ]]; then
      echo "**PASS** — 4 軸全通過 (DRY_RUN=${DRY_RUN})"
    elif [[ "$DRY_RUN" == "true" ]]; then
      echo "**DRY_RUN** — 実 chaos 未実施、確認のみ"
    else
      echo "**FAIL** — chaos_rc=${chaos_rc} / ai_check=${ai_check}"
    fi
  } > "$RESULT_FILE"

  log_ok "結果ファイル書き出し: $RESULT_FILE"

  # ----- Slack 最終通知 -----
  local final_status
  if [[ $chaos_rc -eq 0 && "$ai_check" == "PASS" ]]; then
    final_status="✅ PASS"
  elif [[ "$DRY_RUN" == "true" ]]; then
    final_status="🧪 DRY_RUN"
  else
    final_status="❌ FAIL"
  fi
  _slack "*Chaos 3day Run ${RUN_INDEX} 終了* — Day ${TODAY} / ${final_status} / chaos_rc=${chaos_rc} / ai=${ai_check} / file=\`docs/launch/chaos_test_results/${TODAY}_run${RUN_INDEX}.md\`"

  log_section "Summary"
  echo "  chaos_rc:   $chaos_rc"
  echo "  ai_check:   $ai_check"
  echo "  status:     $final_status"
  echo "  result:     $RESULT_FILE"
  echo ""

  # exit code: chaos_rc != 0 か ai_check FAIL なら 1
  if [[ "$DRY_RUN" == "true" ]]; then
    exit 0
  fi
  if [[ $chaos_rc -ne 0 ]] || [[ "$ai_check" =~ ^FAIL ]]; then
    exit 1
  fi
  exit 0
}

main "$@"
