#!/bin/bash
# scripts/healthcheck_external.sh
# 外形 healthcheck: Cloudflare → nginx → backend のパス全体を確認
# Usage: ./scripts/healthcheck_external.sh [production|staging]
# Exit: 0=全部200, 1=失敗あり
set -euo pipefail

ENV="${1:-production}"
if [[ "$ENV" == "production" ]]; then
  URL="https://api.ultra-auto-trade.com/health"
else
  # staging は CF Access token が必要なのでスキップ
  echo "staging外形チェックはCF Access tokenが必要。スキップ。"
  exit 0
fi

FAIL=0
for i in 1 2 3 4 5; do
  code=$(curl -sf -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null || echo "000")
  echo "[$(date +%H:%M:%S)] $i/5: HTTP $code"
  if [[ "$code" != "200" ]]; then
    FAIL=1
  fi
  sleep 2
done

if [[ "$FAIL" -eq 1 ]]; then
  echo "❌ 外形 healthcheck FAILED: $URL"
  exit 1
else
  echo "✅ 外形 healthcheck OK: $URL"
fi
