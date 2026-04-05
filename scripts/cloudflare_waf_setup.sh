#!/bin/bash
# Cloudflare WAF + Rate Limiting 一括適用スクリプト
#
# 使用方法:
#   CF_API_TOKEN=xxx CF_ZONE_ID=yyy ./scripts/cloudflare_waf_setup.sh [apply|dry-run|status]
#
# 引数:
#   apply   — ルールを適用
#   dry-run — API呼び出しをせず、適用予定のルールを表示（デフォルト）
#   status  — 現在適用されているルールを表示
#
# オプション環境変数:
#   CF_ADMIN_IP — 管理者IPアドレス（設定時のみ admin IP制限ルールを適用）
#
# 詳細: docs/35_cloudflare_waf_config.md

set -euo pipefail

CF_API_TOKEN="${CF_API_TOKEN:?CF_API_TOKEN が未設定です。Cloudflare API Token を設定してください}"
CF_ZONE_ID="${CF_ZONE_ID:?CF_ZONE_ID が未設定です。Cloudflare Zone ID を設定してください}"
CF_API_BASE="https://api.cloudflare.com/client/v4"
MODE="${1:-dry-run}"
CF_ADMIN_IP="${CF_ADMIN_IP:-}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ------------------------------------------------------------
# Cloudflare API ラッパー
# dry-run 時は実際の API 呼び出しを行わない
# ------------------------------------------------------------
cf_api() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local url="${CF_API_BASE}/zones/${CF_ZONE_ID}${path}"

  if [ "$MODE" = "dry-run" ]; then
    log "DRY-RUN: $method $path"
    if [ -n "$data" ]; then
      echo "$data" | python3 -m json.tool 2>/dev/null || echo "$data"
    fi
    # dry-run 用のダミーレスポンスを返す
    echo '{"success": true, "result": {"id": "dry-run-id", "rules": []}}'
    return 0
  fi

  local curl_args=(-s -X "$method" "$url" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json")
  [ -n "$data" ] && curl_args+=(-d "$data")

  local response
  response=$(curl "${curl_args[@]}")

  local success
  success=$(echo "$response" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "False")

  if [ "$success" != "True" ]; then
    log "ERROR: API 呼び出し失敗: $method $path"
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    return 1
  fi

  echo "$response"
}

# ------------------------------------------------------------
# Custom WAF Rules
# Cloudflare Rulesets API (phase: http_request_firewall_custom)
# https://developers.cloudflare.com/waf/custom-rules/create-api/
# ------------------------------------------------------------
apply_custom_rules() {
  log "=== Custom WAF Rules 適用 ==="

  # ルール一覧を組み立て
  local rules
  rules='[
    {
      "action": "block",
      "expression": "(http.request.uri.path eq \"/docs\" or http.request.uri.path eq \"/openapi.json\" or http.request.uri.path eq \"/redoc\")",
      "description": "Block-Sensitive-Paths",
      "enabled": true
    },
    {
      "action": "block",
      "expression": "(http.user_agent contains \"sqlmap\" or http.user_agent contains \"nikto\" or http.user_agent contains \"dirbuster\" or http.user_agent contains \"nmap\" or http.user_agent contains \"masscan\")",
      "description": "Block-Bad-UA",
      "enabled": true
    },
    {
      "action": "managed_challenge",
      "expression": "(http.request.uri.path contains \"/auth\" and ip.geoip.country ne \"JP\")",
      "description": "Challenge-Non-JP-Auth",
      "enabled": true
    }'

  # 管理者IP制限ルール（CF_ADMIN_IP が設定されている場合のみ）
  if [ -n "$CF_ADMIN_IP" ]; then
    log "Admin IP ルールを追加: $CF_ADMIN_IP"
    rules="${rules},
    {
      \"action\": \"block\",
      \"expression\": \"(http.request.uri.path contains \\\"/admin\\\" and ip.src ne ${CF_ADMIN_IP})\",
      \"description\": \"Block-Admin-NonIP\",
      \"enabled\": true
    }"
  else
    log "SKIP: Admin IP ルール（CF_ADMIN_IP が未設定）"
  fi

  rules="${rules}]"

  log "Custom Rules を適用中..."
  cf_api PUT "/rulesets/phases/http_request_firewall_custom/entrypoint" \
    "{\"rules\": ${rules}}" > /dev/null

  log "Custom Rules 適用完了"
}

# ------------------------------------------------------------
# Rate Limiting Rules
# Cloudflare Rulesets API (phase: http_ratelimit)
# https://developers.cloudflare.com/waf/rate-limiting-rules/create-api/
# ------------------------------------------------------------
apply_rate_limiting() {
  log "=== Rate Limiting Rules 適用 ==="

  local rules='[
    {
      "description": "Auth brute force: 5 req/60s",
      "expression": "(http.request.uri.path eq \"/auth/login\" and http.request.method eq \"POST\")",
      "action": "block",
      "action_parameters": {
        "response": {
          "status_code": 429,
          "content": "{\"detail\": \"Too many requests\"}",
          "content_type": "application/json"
        }
      },
      "ratelimit": {
        "characteristics": ["ip.src"],
        "period": 60,
        "requests_per_period": 5,
        "mitigation_timeout": 600
      },
      "enabled": true
    },
    {
      "description": "Register protection: 3 req/600s",
      "expression": "(http.request.uri.path eq \"/auth/register\" and http.request.method eq \"POST\")",
      "action": "block",
      "action_parameters": {
        "response": {
          "status_code": 429,
          "content": "{\"detail\": \"Too many requests\"}",
          "content_type": "application/json"
        }
      },
      "ratelimit": {
        "characteristics": ["ip.src"],
        "period": 600,
        "requests_per_period": 3,
        "mitigation_timeout": 3600
      },
      "enabled": true
    },
    {
      "description": "API general: 60 req/60s",
      "expression": "(http.request.uri.path contains \"/api/\")",
      "action": "block",
      "action_parameters": {
        "response": {
          "status_code": 429,
          "content": "{\"detail\": \"Too many requests\"}",
          "content_type": "application/json"
        }
      },
      "ratelimit": {
        "characteristics": ["ip.src"],
        "period": 60,
        "requests_per_period": 60,
        "mitigation_timeout": 300
      },
      "enabled": true
    },
    {
      "description": "Aave rebalance: 2 req/600s",
      "expression": "(http.request.uri.path contains \"/aave/rebalance\" and http.request.method eq \"POST\")",
      "action": "block",
      "action_parameters": {
        "response": {
          "status_code": 429,
          "content": "{\"detail\": \"Too many requests\"}",
          "content_type": "application/json"
        }
      },
      "ratelimit": {
        "characteristics": ["ip.src"],
        "period": 600,
        "requests_per_period": 2,
        "mitigation_timeout": 1800
      },
      "enabled": true
    },
    {
      "description": "Emergency stop: 3 req/60s",
      "expression": "(http.request.uri.path contains \"/emergency-stop\" and http.request.method eq \"POST\")",
      "action": "block",
      "action_parameters": {
        "response": {
          "status_code": 429,
          "content": "{\"detail\": \"Too many requests\"}",
          "content_type": "application/json"
        }
      },
      "ratelimit": {
        "characteristics": ["ip.src"],
        "period": 60,
        "requests_per_period": 3,
        "mitigation_timeout": 300
      },
      "enabled": true
    }
  ]'

  log "Rate Limiting Rules を適用中..."
  cf_api PUT "/rulesets/phases/http_ratelimit/entrypoint" \
    "{\"rules\": ${rules}}" > /dev/null

  log "Rate Limiting Rules 適用完了"
}

# ------------------------------------------------------------
# Managed Rulesets
# https://developers.cloudflare.com/waf/managed-rules/deploy-api/
# ------------------------------------------------------------
enable_managed_rulesets() {
  log "=== Managed Rulesets 有効化 ==="

  # Cloudflare Managed Ruleset (ID固定値: efb7b8c949ac4650a09736fc376e9aee)
  # OWASP Core Ruleset (ID固定値: 4814384a9e5d4991b9815dcfc25d2f1f)
  local rules='[
    {
      "action": "execute",
      "action_parameters": {
        "id": "efb7b8c949ac4650a09736fc376e9aee",
        "version": "latest"
      },
      "expression": "true",
      "description": "Cloudflare Managed Ruleset",
      "enabled": true
    },
    {
      "action": "execute",
      "action_parameters": {
        "id": "4814384a9e5d4991b9815dcfc25d2f1f",
        "version": "latest",
        "overrides": {
          "action": "block",
          "sensitivity_level": "medium"
        }
      },
      "expression": "true",
      "description": "OWASP Core Ruleset (medium sensitivity)",
      "enabled": true
    }
  ]'

  log "Managed Rulesets を有効化中..."
  cf_api PUT "/rulesets/phases/http_request_firewall_managed/entrypoint" \
    "{\"rules\": ${rules}}" > /dev/null

  log "Managed Rulesets 有効化完了"
}

# ------------------------------------------------------------
# Status check — 現在適用中のルールを表示
# ------------------------------------------------------------
show_status() {
  log "=== 現在の Custom WAF Rules ==="
  cf_api GET "/rulesets/phases/http_request_firewall_custom/entrypoint" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    rules = data.get('result', {}).get('rules', [])
    if not rules:
        print('  (ルールなし)')
    for r in rules:
        status = 'enabled' if r.get('enabled') else 'disabled'
        print(f\"  [{r.get('action','?')}] {r.get('description','(no desc)')} — {status}\")
except Exception as e:
    print(f'  (取得失敗: {e})')
" 2>/dev/null

  log "=== 現在の Rate Limiting Rules ==="
  cf_api GET "/rulesets/phases/http_ratelimit/entrypoint" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    rules = data.get('result', {}).get('rules', [])
    if not rules:
        print('  (ルールなし)')
    for r in rules:
        rl = r.get('ratelimit', {})
        reqs = rl.get('requests_per_period', '?')
        period = rl.get('period', '?')
        status = 'enabled' if r.get('enabled') else 'disabled'
        print(f\"  [{r.get('action','?')}] {r.get('description','')} — {reqs}req/{period}s [{status}]\")
except Exception as e:
    print(f'  (取得失敗: {e})')
" 2>/dev/null

  log "=== 現在の Managed Rulesets ==="
  cf_api GET "/rulesets/phases/http_request_firewall_managed/entrypoint" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    rules = data.get('result', {}).get('rules', [])
    if not rules:
        print('  (ルールなし)')
    for r in rules:
        params = r.get('action_parameters', {})
        ruleset_id = params.get('id', '?')
        status = 'enabled' if r.get('enabled') else 'disabled'
        print(f\"  [execute] {r.get('description', ruleset_id)} — {status}\")
except Exception as e:
    print(f'  (取得失敗: {e})')
" 2>/dev/null
}

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
case "$MODE" in
  apply)
    log "=== Cloudflare WAF ルール適用開始 (Zone: $CF_ZONE_ID) ==="
    apply_custom_rules
    apply_rate_limiting
    enable_managed_rulesets
    log "=== 適用完了 ==="
    log "NOTE: Cloudflare Analytics でブロック状況を2週間モニタリングしてください"
    log "NOTE: 誤検知が発生した場合は docs/35_cloudflare_waf_config.md の手順を参照"
    ;;
  dry-run)
    log "=== DRY-RUN モード（API呼び出しなし） ==="
    apply_custom_rules
    apply_rate_limiting
    enable_managed_rulesets
    log "=== DRY-RUN 完了 ==="
    log "実際に適用するには: CF_API_TOKEN=xxx CF_ZONE_ID=yyy $0 apply"
    ;;
  status)
    log "=== WAF ルール確認 (Zone: $CF_ZONE_ID) ==="
    show_status
    ;;
  *)
    echo "Usage: CF_API_TOKEN=xxx CF_ZONE_ID=yyy $0 [apply|dry-run|status]"
    echo ""
    echo "  apply   — ルールを適用"
    echo "  dry-run — 適用予定のルールを表示（デフォルト）"
    echo "  status  — 現在のルールを表示"
    echo ""
    echo "オプション:"
    echo "  CF_ADMIN_IP=x.x.x.x  — 管理者IP制限ルールを追加"
    exit 1
    ;;
esac
