#!/usr/bin/env bash
# scripts/chaos_test_staging.sh
#
# Ultra AutoTrade Chaos Test — staging 自動復旧検証
# ローンチ条件2: コンテナの main プロセスを host から SIGKILL (クラッシュ再現)
#   → restart:always による 5分以内自動復旧を確認
# 注意: `docker kill` は使わない (Docker が意図的停止扱いし restart:always が発火しないため。
#   2026-06-11 実機確認)。root か sudo で実行すること (host PID への kill -9 が必要)。
#
# 対象: staging 環境のみ（production は絶対に触らない）
# 実行場所: 本番 Hetzner VPS (77.42.46.155) または dev VPS
#
# 使い方:
#   bash scripts/chaos_test_staging.sh          # staging で全コンテナ検証
#   DRY_RUN=true bash scripts/chaos_test_staging.sh  # dry-run (kill しない)
#   TARGET_CONTAINER=ultra-autotrade-nginx-staging bash scripts/chaos_test_staging.sh  # 1つだけ
#
# 環境変数:
#   DRY_RUN                true の場合 kill をスキップしてレポートのみ
#   SLACK_WEBHOOK_URL      結果通知先（未設定時は .env.production から読み込み）
#   HEALTH_URL_STAGING     staging /health URL (default: http://127.0.0.1:8082/health)
#   MAX_RECOVERY_SEC       復旧タイムアウト秒数 (default: 300 = 5分)
#   TARGET_CONTAINER       対象コンテナ名（未設定時は全 staging コンテナ）

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
SCRIPT_NAME="chaos_test_staging"
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"
DRY_RUN="${DRY_RUN:-false}"
HEALTH_URL_STAGING="${HEALTH_URL_STAGING:-http://127.0.0.1:8082/health}"
MAX_RECOVERY_SEC="${MAX_RECOVERY_SEC:-300}"
TARGET_CONTAINER="${TARGET_CONTAINER:-}"
CURL_TIMEOUT=5

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# Slack 通知
# =============================================================================
_load_slack_webhook() {
  if [[ -z "${SLACK_WEBHOOK_URL:-}" && -f "$ENV_FILE" ]]; then
    SLACK_WEBHOOK_URL=$(grep '^SLACK_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'") || true
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
# ユーティリティ
# =============================================================================
log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()      { echo -e "${GREEN}[PASS]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_fail()    { echo -e "${RED}[FAIL]${NC}  $*"; }
log_section() { echo -e "\n${BLUE}===== $* =====${NC}"; }

# =============================================================================
# 安全ガード
# =============================================================================
_safety_check() {
  log_section "Safety Check"

  # production コンテナが指定されていたら即終了
  if [[ "$TARGET_CONTAINER" == *"production"* ]]; then
    log_fail "ERROR: production コンテナは chaos test 対象外。staging のみ許可。"
    exit 1
  fi

  # staging コンテナの存在確認
  local staging_count
  staging_count=$(docker ps --filter "name=staging" --format "{{.Names}}" | wc -l)
  if [[ "$staging_count" -eq 0 ]]; then
    log_warn "staging コンテナが見つかりません。本番 VPS で実行してください。"
    log_warn "または: ssh -i ~/.ssh/hetzner_direct ultra@77.42.46.155 'bash /opt/ultra-autotrade/scripts/chaos_test_staging.sh'"
    exit 1
  fi

  log_ok "staging コンテナ数: $staging_count"

  if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY_RUN モード: コンテナ kill はスキップします"
  fi
}

# =============================================================================
# health チェック
# =============================================================================
_check_health() {
  local url="$1"
  local http_code
  http_code=$(curl -sf -o /dev/null -w "%{http_code}" --max-time "$CURL_TIMEOUT" "$url" 2>/dev/null) || http_code="000"
  echo "$http_code"
}

_wait_for_recovery() {
  local container="$1"
  local health_url="$2"
  local start_time=$SECONDS
  local elapsed=0
  local interval=5

  log_info "復旧待機中... (最大 ${MAX_RECOVERY_SEC}秒)"

  while [[ $elapsed -lt $MAX_RECOVERY_SEC ]]; do
    sleep "$interval"
    elapsed=$(( SECONDS - start_time ))

    # コンテナが running か確認
    local status
    status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null) || status="unknown"

    if [[ "$status" == "running" ]]; then
      # 該当コンテナ自身の healthcheck を確認する。
      # 旧実装は全コンテナを単一 nginx URL (8082) で判定していたため、nginx/backend を
      # kill した瞬間に health が落ち、以降の全コンテナ判定が連鎖 FAIL していた
      # (2026-06-11 実機確認)。healthcheck 未定義のコンテナは running で復旧とみなす。
      # end-to-end の nginx health は最後に _final_health_check でまとめて確認する。
      local health
      health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null) || health="none"
      if [[ "$health" == "healthy" || "$health" == "none" ]]; then
        echo "$elapsed"
        return 0
      fi
    fi

    echo -ne "\r  ${elapsed}秒経過... (container: ${status})"
  done

  echo ""
  echo "-1"  # タイムアウト
  return 1
}

# =============================================================================
# コンテナ別 chaos テスト
# =============================================================================
_test_container() {
  local container="$1"
  local health_url="$2"
  local result_var="$3"

  log_section "Chaos Test: $container"

  # kill 前の状態確認
  local pre_status
  pre_status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null) || {
    log_warn "コンテナが存在しません: $container (スキップ)"
    eval "$result_var=skip"
    return 0
  }
  log_info "kill 前の状態: $pre_status"

  # kill 前 health 確認
  local pre_health
  pre_health=$(_check_health "$health_url")
  log_info "kill 前 health: HTTP $pre_health"

  if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY_RUN: kill をスキップ"
    eval "$result_var=dry_run"
    return 0
  fi

  # コンテナの main プロセスを host から SIGKILL してクラッシュを再現する。
  # 重要: `docker kill` は Docker が「意図的停止」と扱うため restart:always が
  # 発火しない (2026-06-11 実機確認: docker kill → RestartCount=0 で復帰せず)。
  # 本番のクラッシュ (OOM/panic) は host kill -9 と同経路で、restart:always が発火する
  # (実機確認: host kill -9 → RestartCount 0→1 で自動復帰)。
  local cpid
  cpid=$(docker inspect -f '{{.State.Pid}}' "$container" 2>/dev/null) || cpid=""
  if [[ -z "$cpid" || "$cpid" == "0" ]]; then
    log_warn "host PID 取得失敗: $container (スキップ)"
    eval "$result_var=skip"
    return 0
  fi
  log_info "プロセスクラッシュ再現: host kill -9 PID=$cpid ($container) ..."
  if ! kill -9 "$cpid" 2>/dev/null; then
    # 非 root の場合は sudo で再試行 (root 実行推奨)
    sudo kill -9 "$cpid" 2>/dev/null || {
      log_warn "kill 失敗 (権限不足の可能性): $container — root か sudo で実行してください"
      eval "$result_var=skip"
      return 0
    }
  fi
  log_info "クラッシュ再現完了。自動復旧を待機..."

  # 復旧待機
  local recovery_sec
  recovery_sec=$(_wait_for_recovery "$container" "$health_url")
  echo ""

  if [[ "$recovery_sec" -ge 0 ]] 2>/dev/null; then
    log_ok "復旧成功: ${recovery_sec}秒 (${container})"
    eval "$result_var=${recovery_sec}"
  else
    log_fail "復旧失敗: タイムアウト (${MAX_RECOVERY_SEC}秒超過)"
    eval "$result_var=timeout"
  fi
}

# =============================================================================
# 全体 health チェック (テスト後)
# =============================================================================
_final_health_check() {
  log_section "Final Health Check"

  local http_code
  http_code=$(_check_health "$HEALTH_URL_STAGING")

  if [[ "$http_code" == "200" ]]; then
    log_ok "staging /health: HTTP 200"
    return 0
  else
    log_fail "staging /health: HTTP $http_code"
    return 1
  fi
}

# =============================================================================
# メイン
# =============================================================================
main() {
  local start_time=$SECONDS

  echo ""
  log_section "Ultra AutoTrade Chaos Test — staging"
  echo "  実行時刻: $(date '+%Y-%m-%d %H:%M:%S JST')"
  echo "  DRY_RUN:  $DRY_RUN"
  echo "  最大復旧待機: ${MAX_RECOVERY_SEC}秒"
  echo ""

  _load_slack_webhook
  _safety_check

  # テスト対象コンテナ一覧
  declare -a containers
  if [[ -n "$TARGET_CONTAINER" ]]; then
    containers=("$TARGET_CONTAINER")
  else
    # staging コンテナを自動検出（production は除外）
    while IFS= read -r name; do
      if [[ "$name" != *"production"* ]]; then
        containers+=("$name")
      fi
    done < <(docker ps --filter "name=staging" --format "{{.Names}}" | sort)
  fi

  if [[ ${#containers[@]} -eq 0 ]]; then
    log_warn "テスト対象コンテナなし"
    exit 0
  fi

  log_info "テスト対象コンテナ: ${#containers[@]} 件"
  for c in "${containers[@]}"; do
    echo "  - $c"
  done

  # 初期 health 確認
  log_section "Pre-test Health Check"
  local pre_health
  pre_health=$(_check_health "$HEALTH_URL_STAGING")
  if [[ "$pre_health" != "200" ]]; then
    log_warn "テスト前から staging が応答なし (HTTP $pre_health)。nginx/backend 確認を先に実施してください。"
    # 終了せず続行（コンテナ再起動テストは可能）
  else
    log_ok "Pre-test: HTTP 200"
  fi

  # Slack 開始通知
  _slack "🔥 *Chaos Test 開始* — staging コンテナ kill → 自動復旧検証 (${#containers[@]} コンテナ)"

  # 各コンテナのテスト結果を記録
  declare -A results

  # 重要度の高いサービスから順にテスト（依存関係を考慮）
  # postgres → backend → nginx の順（postgres は最後にした方が安全だが、依存テストの観点から順に）
  declare -a ordered_containers
  local -a high_priority=("nginx" "backend")
  local -a low_priority=("postgres" "frontend" "cloudflared")

  # 優先度順に並び替え
  for priority in "${high_priority[@]}"; do
    for c in "${containers[@]}"; do
      if [[ "$c" == *"$priority"* ]]; then
        ordered_containers+=("$c")
      fi
    done
  done
  for priority in "${low_priority[@]}"; do
    for c in "${containers[@]}"; do
      if [[ "$c" == *"$priority"* ]]; then
        ordered_containers+=("$c")
      fi
    done
  done
  # 残り（順序に含まれないもの）
  for c in "${containers[@]}"; do
    local found=false
    for oc in "${ordered_containers[@]:-}"; do
      [[ "$c" == "$oc" ]] && found=true && break
    done
    [[ "$found" == "false" ]] && ordered_containers+=("$c")
  done

  # テスト実行
  local pass_count=0
  local fail_count=0
  local skip_count=0

  for container in "${ordered_containers[@]}"; do
    local result=""
    _test_container "$container" "$HEALTH_URL_STAGING" "result"
    results["$container"]="$result"

    case "$result" in
      timeout)
        (( fail_count++ )) || true
        _slack "❌ *Chaos Fail* — \`$container\` タイムアウト (${MAX_RECOVERY_SEC}秒超過)"
        ;;
      skip|dry_run)
        (( skip_count++ )) || true
        ;;
      *)
        (( pass_count++ )) || true
        ;;
    esac

    # コンテナ間のインターバル（次のテスト前に staging を安定させる）
    if [[ "$result" != "skip" && "$result" != "dry_run" && "$result" != "timeout" ]]; then
      log_info "次テストまで 15 秒待機..."
      sleep 15
    fi
  done

  # 最終 health 確認
  _final_health_check
  local final_ok=$?

  # 経過時間
  local total_sec=$(( SECONDS - start_time ))

  # サマリー出力
  log_section "Chaos Test Summary"
  echo ""
  printf "  %-45s %s\n" "コンテナ" "結果"
  printf "  %s\n" "$(printf '%.0s-' {1..60})"
  for container in "${ordered_containers[@]}"; do
    local r="${results[$container]:-skip}"
    if [[ "$r" == "timeout" ]]; then
      printf "  %-45s ${RED}FAIL (timeout)${NC}\n" "$container"
    elif [[ "$r" == "skip" || "$r" == "dry_run" ]]; then
      printf "  %-45s ${YELLOW}SKIP${NC}\n" "$container"
    else
      printf "  %-45s ${GREEN}PASS (%ss)${NC}\n" "$container" "$r"
    fi
  done
  echo ""
  echo "  通過: $pass_count  失敗: $fail_count  スキップ: $skip_count"
  echo "  所要時間: ${total_sec}秒"
  echo ""

  # Slack 最終通知
  if [[ $fail_count -eq 0 && $final_ok -eq 0 ]]; then
    local summary="✅ *Chaos Test PASS* — staging 全コンテナ自動復旧確認\\nPASS: $pass_count / SKIP: $skip_count / 所要: ${total_sec}s"
    _slack "$summary"
    log_ok "Chaos Test PASS"
  else
    local summary="❌ *Chaos Test FAIL* — staging 復旧失敗\\nFAIL: $fail_count / PASS: $pass_count / SKIP: $skip_count / 所要: ${total_sec}s"
    _slack "$summary"
    log_fail "Chaos Test FAIL"
    exit 1
  fi
}

main "$@"
