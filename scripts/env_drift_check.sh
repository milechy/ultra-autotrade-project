#!/usr/bin/env bash
# =============================================================================
# env_drift_check.sh — 環境間設定 drift 検知スクリプト
#
# 背景:
#   2026-05-01 production cloudflared ingress 修正後、staging への水平展開漏れで
#   2026-05-09 に同型 502 が 12 日遅延検出された (postmortem: docs/postmortems/2026-05-09_staging_api_502.md)。
#   production hotfix が staging に横展開されているかを自動検知するために作成。
#
# チェック内容:
#   1. cloudflared config.yml の ingress port vs compose nginx 公開 port
#   2. nginx upstream.conf のバックエンドポート vs compose backend 内部ポート
#   3. production compose と staging compose の nginx 公開ポート比較
#   4. staging cloudflared config ファイルが存在する場合の ingress port 一致
#
# 使用方法:
#   bash scripts/env_drift_check.sh
#   bash scripts/env_drift_check.sh --slack  # Slack通知付き
#   bash scripts/env_drift_check.sh --quiet  # 差異ありのみ出力
#
# 終了コード:
#   0: drift なし (全チェック通過)
#   1: drift 検出 (要確認)
#   2: チェックエラー (ファイル不存在等)
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ─── オプション解析 ───────────────────────────────────────────────────
SLACK_NOTIFY=false
QUIET=false
for arg in "$@"; do
  case "$arg" in
    --slack) SLACK_NOTIFY=true ;;
    --quiet) QUIET=true ;;
  esac
done

# ─── 設定ファイルパス ─────────────────────────────────────────────────
COMPOSE_PROD="${PROJECT_ROOT}/docker-compose.production.yml"
COMPOSE_STAGING="${PROJECT_ROOT}/docker-compose.staging.yml"
CF_CONFIG="${PROJECT_ROOT}/config/cloudflared/config.yml"
CF_CONFIG_STAGING="${PROJECT_ROOT}/config/cloudflared/config.staging.yml"
UPSTREAM_PROD="${PROJECT_ROOT}/docker/nginx/upstream.production.conf"
UPSTREAM_STAGING="${PROJECT_ROOT}/docker/nginx/upstream.staging.conf"

# ─── 出力ヘルパー ────────────────────────────────────────────────────
log()      { echo "[drift-check] $*"; }
ok()       { echo "  ✅ $*"; }
warn()     { echo "  ⚠️  $*"; WARNINGS+=("$*"); }
fail()     { echo "  ❌ $*"; DRIFT+=("$*"); }
skip()     { "${QUIET}" || echo "  ⬜ $*"; }

DRIFT=()
WARNINGS=()

# ─── ヘルパー関数 ────────────────────────────────────────────────────

# compose ファイルから nginx サービスの全公開ホストポートをスペース区切りで取得
# "8000:8080" → 8000、"127.0.0.1:8082:8080" → 8082
get_nginx_host_ports() {
  local compose_file="$1"
  # nginx サービスの ports ブロックから全ホストポートを抽出
  awk '
    /^  nginx:/{in_nginx=1; next}
    in_nginx && /^  [a-z]/ && !/^  nginx:/{in_nginx=0}
    in_nginx && /^\s+- /{
      line=$0
      # "IP:HOST_PORT:CONTAINER_PORT" or "HOST_PORT:CONTAINER_PORT"
      if (match(line, /[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:([0-9]+):[0-9]+/, arr)) {
        print arr[1]
      } else if (match(line, /"?([0-9]+):[0-9]+"?/, arr)) {
        print arr[1]
      }
    }
  ' "${compose_file}" 2>/dev/null
}

# 後方互換: 最初のポートのみ取得
get_nginx_host_port() {
  get_nginx_host_ports "$1" | head -1
}

# compose ファイルから backend-blue サービスの uvicorn 内部ポートを取得
# command: の "--port 8000" から抽出
get_backend_internal_port() {
  local compose_file="$1"
  # command ブロック内の --port N を探す（複数行 YAML の > 形式に対応）
  awk '
    /^  backend-blue:/{in_service=1}
    in_service && /^  [a-z]/ && !/^  backend-blue:/{in_service=0}
    in_service && /--port/{
      match($0, /--port[[:space:]]+([0-9]+)/, arr)
      if (arr[1] != "") { print arr[1]; exit }
    }
  ' "${compose_file}" 2>/dev/null | head -1
}

# cloudflared config.yml から特定 hostname の service port を取得
get_cf_ingress_port() {
  local config_file="$1"
  local hostname="$2"
  # hostname の直後の service 行からポート番号を抽出
  awk -v host="${hostname}" '
    /hostname:.*'"${hostname}"'/{found=1; next}
    found && /service:/{
      match($0, /localhost:([0-9]+)/, arr)
      if (arr[1] != "") { print arr[1]; exit }
      found=0
    }
    found && /hostname:/{found=0}
  ' "${config_file}" 2>/dev/null | head -1
}

# nginx upstream.conf からバックエンドのポートを取得
# "set $backend backend-blue:8000;" → 8000
get_upstream_backend_port() {
  local upstream_file="$1"
  grep -E 'set \$backend backend-(blue|green):' "${upstream_file}" 2>/dev/null \
    | grep -oE ':[0-9]+' | tr -d ':' | head -1
}

# ─── チェック 1: production cloudflared ingress port vs nginx 公開 port ───────
log "=== Check 1: production cloudflared ingress port vs nginx ホストポート ==="

if [[ ! -f "${CF_CONFIG}" ]]; then
  warn "config/cloudflared/config.yml が存在しない（token 方式 = Dashboard 管理）。手動確認が必要。"
  warn "  確認先: Cloudflare Dashboard → Tunnels → ultra-autotrade → Public Hostname"
  warn "  確認内容: api.ultra-auto-trade.com の Service が http://localhost:<nginx_port> か"
else
  if [[ ! -f "${COMPOSE_PROD}" ]]; then
    fail "docker-compose.production.yml が存在しない"
  else
    cf_api_port=$(get_cf_ingress_port "${CF_CONFIG}" "api.ultra-auto-trade.com")
    nginx_prod_ports=$(get_nginx_host_ports "${COMPOSE_PROD}" | tr '\n' ' ')

    if [[ -z "${cf_api_port}" ]]; then
      warn "config.yml から api.ultra-auto-trade.com の ingress port を取得できなかった"
    elif [[ -z "${nginx_prod_ports}" ]]; then
      warn "docker-compose.production.yml から nginx ホストポートを取得できなかった"
    elif echo "${nginx_prod_ports}" | grep -qw "${cf_api_port}"; then
      ok "production cloudflared ingress port (${cf_api_port}) が nginx ホストポート (${nginx_prod_ports}) に含まれる"
    else
      fail "production cloudflared ingress port (${cf_api_port}) が nginx ホストポート (${nginx_prod_ports}) にない"
      fail "  → Cloudflare Dashboard または config.yml の ingress を nginx の公開ポートに合わせる"
    fi
  fi
fi

echo ""

# ─── チェック 2: staging cloudflared ingress port (config ファイルがある場合) ───
log "=== Check 2: staging cloudflared ingress port vs nginx ホストポート ==="

if [[ ! -f "${CF_CONFIG_STAGING}" ]]; then
  warn "config/cloudflared/config.staging.yml が存在しない（token 方式 = Dashboard 管理）。手動確認が必要。"
  if [[ -f "${COMPOSE_STAGING}" ]]; then
    nginx_staging_port=$(get_nginx_host_port "${COMPOSE_STAGING}")
    warn "  staging nginx ホストポート: ${nginx_staging_port:-不明}"
    warn "  確認先: Cloudflare Dashboard → Tunnels → ultra-autotrade-staging → Public Hostname"
    warn "  確認内容: api-staging.ultra-auto-trade.com の Service が http://localhost:${nginx_staging_port:-?} か"
  fi
else
  if [[ ! -f "${COMPOSE_STAGING}" ]]; then
    fail "docker-compose.staging.yml が存在しない"
  else
    cf_staging_port=$(get_cf_ingress_port "${CF_CONFIG_STAGING}" "api-staging.ultra-auto-trade.com")
    nginx_staging_port=$(get_nginx_host_port "${COMPOSE_STAGING}")

    if [[ -z "${cf_staging_port}" ]]; then
      warn "config.staging.yml から api-staging の ingress port を取得できなかった"
    elif [[ -z "${nginx_staging_port}" ]]; then
      warn "docker-compose.staging.yml から nginx ホストポートを取得できなかった"
    elif [[ "${cf_staging_port}" != "${nginx_staging_port}" ]]; then
      fail "staging cloudflared ingress port (${cf_staging_port}) != nginx ホストポート (${nginx_staging_port})"
      fail "  → config.staging.yml の ingress を localhost:${nginx_staging_port} に更新する"
    else
      ok "staging cloudflared ingress port (${cf_staging_port}) == nginx ホストポート (${nginx_staging_port})"
    fi
  fi
fi

echo ""

# ─── チェック 3: nginx upstream backend port vs compose backend 内部ポート ───
log "=== Check 3: nginx upstream バックエンドポート vs compose backend 内部ポート ==="

for env in production staging; do
  if [[ "${env}" == "production" ]]; then
    compose_file="${COMPOSE_PROD}"
    upstream_file="${UPSTREAM_PROD}"
  else
    compose_file="${COMPOSE_STAGING}"
    upstream_file="${UPSTREAM_STAGING}"
  fi

  if [[ ! -f "${upstream_file}" ]]; then
    warn "${env}: ${upstream_file} が存在しない"
    continue
  fi
  if [[ ! -f "${compose_file}" ]]; then
    warn "${env}: ${compose_file} が存在しない"
    continue
  fi

  upstream_port=$(get_upstream_backend_port "${upstream_file}")
  backend_internal_port=$(get_backend_internal_port "${compose_file}")

  if [[ -z "${upstream_port}" ]]; then
    warn "${env}: upstream.conf からバックエンドポートを取得できなかった"
  elif [[ -z "${backend_internal_port}" ]]; then
    warn "${env}: compose から backend-blue 内部ポートを取得できなかった"
  elif [[ "${upstream_port}" != "${backend_internal_port}" ]]; then
    fail "${env}: nginx upstream ポート (${upstream_port}) != backend 内部ポート (${backend_internal_port})"
  else
    ok "${env}: nginx upstream (${upstream_port}) == backend 内部ポート (${backend_internal_port})"
  fi
done

echo ""

# ─── チェック 4: production nginx ポートと staging nginx ポートの相対関係 ───
log "=== Check 4: compose ファイル間の nginx ポート重複チェック ==="

if [[ -f "${COMPOSE_PROD}" ]] && [[ -f "${COMPOSE_STAGING}" ]]; then
  prod_nginx_port=$(get_nginx_host_port "${COMPOSE_PROD}")
  staging_nginx_port=$(get_nginx_host_port "${COMPOSE_STAGING}")

  if [[ -n "${prod_nginx_port}" ]] && [[ -n "${staging_nginx_port}" ]]; then
    if [[ "${prod_nginx_port}" == "${staging_nginx_port}" ]]; then
      fail "production nginx ポート (${prod_nginx_port}) と staging nginx ポート (${staging_nginx_port}) が同じ！ポート衝突リスク。"
    else
      ok "production nginx ポート (${prod_nginx_port}) != staging nginx ポート (${staging_nginx_port}) (衝突なし)"
    fi
  else
    warn "一方または両方の compose から nginx ポートを取得できなかった (prod=${prod_nginx_port:-不明} / staging=${staging_nginx_port:-不明})"
  fi
fi

echo ""

# ─── チェック 5: horizontal propagation — production の hotfix が staging に展開されているか ───
log "=== Check 5: upstream.conf の upstream 形式チェック (IP 固着バグ再発防止) ==="

for env in production staging; do
  if [[ "${env}" == "production" ]]; then
    upstream_file="${UPSTREAM_PROD}"
  else
    upstream_file="${UPSTREAM_STAGING}"
  fi

  if [[ ! -f "${upstream_file}" ]]; then
    skip "${env}: ${upstream_file} が存在しない"
    continue
  fi

  # 旧形式: "server backend-blue:8000 ...;"  ← IP 固着バグ (nginx 起動時 1 回しか解決しない)
  # 新形式: "set $backend backend-blue:8000;" ← 変数 + resolver で動的解決
  if grep -qE '^[[:space:]]*server backend-(blue|green):' "${upstream_file}"; then
    fail "${env}: upstream.conf が旧形式 (server backend-...) → IP 固着バグ。新形式 (set \$backend) に移行が必要。"
    fail "  参照: docs/postmortems/2026-05-12_nginx_upstream_ip_pin.md"
  elif grep -qE 'set \$backend backend-(blue|green):' "${upstream_file}"; then
    ok "${env}: upstream.conf が新形式 (set \$backend backend-...) で IP 固着バグなし"
  else
    warn "${env}: upstream.conf の形式を判定できなかった (手動確認推奨)"
  fi
done

echo ""

# ─── 結果サマリ ──────────────────────────────────────────────────────
echo "=== 結果サマリ ==="

if [[ "${#WARNINGS[@]}" -gt 0 ]]; then
  echo "⚠️  警告: ${#WARNINGS[@]} 件 (手動確認が必要)"
  for w in "${WARNINGS[@]}"; do
    echo "   - ${w}"
  done
fi

if [[ "${#DRIFT[@]}" -eq 0 ]]; then
  echo "✅ drift なし: 全チェック通過"
  RESULT_STATUS="PASS"
  EXIT_CODE=0
else
  echo "❌ drift 検出: ${#DRIFT[@]} 件"
  for d in "${DRIFT[@]}"; do
    echo "   - ${d}"
  done
  RESULT_STATUS="FAIL"
  EXIT_CODE=1
fi

echo ""
log "横展開チェックリスト: docs/51_horizontal_propagation_checklist.md を参照"

# ─── Slack 通知 ───────────────────────────────────────────────────────
if "${SLACK_NOTIFY}" && [[ "${RESULT_STATUS}" == "FAIL" || "${#WARNINGS[@]}" -gt 0 ]]; then
  WEBHOOK="${SLACK_WEBHOOK_URL:-}"
  if [[ -z "${WEBHOOK}" ]]; then
    log "WARN: SLACK_WEBHOOK_URL が未設定のため Slack 通知をスキップ"
  else
    DRIFT_TEXT=$(printf '%s\n' "${DRIFT[@]:-}" | head -5)
    WARN_TEXT=$(printf '%s\n' "${WARNINGS[@]:-}" | head -3)
    MSG="*[env_drift_check] ${RESULT_STATUS}*\n\n"
    if [[ "${#DRIFT[@]}" -gt 0 ]]; then
      MSG+="❌ drift 検出 (${#DRIFT[@]} 件):\n\`\`\`${DRIFT_TEXT}\`\`\`\n"
    fi
    if [[ "${#WARNINGS[@]}" -gt 0 ]]; then
      MSG+="⚠️  手動確認 (${#WARNINGS[@]} 件):\n\`\`\`${WARN_TEXT}\`\`\`\n"
    fi
    MSG+="\n参照: docs/51_horizontal_propagation_checklist.md"

    curl -s -X POST "${WEBHOOK}" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"${MSG}\"}" > /dev/null 2>&1 || true
  fi
fi

exit "${EXIT_CODE}"
