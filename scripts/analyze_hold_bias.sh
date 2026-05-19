#!/bin/bash
# scripts/analyze_hold_bias.sh
# AI判定のHOLD偏向分析スクリプト
# production DBに直接接続せずAPI経由で確認する
# Usage: ./scripts/analyze_hold_bias.sh [--days N] [--api-url URL]
set -euo pipefail

DAYS="${DAYS:-7}"
API_URL="${API_URL:-https://api.ultra-auto-trade.com}"

echo "=== AI判定 HOLD偏向分析 (直近${DAYS}日) ==="
echo "API: $API_URL"
echo ""

# /ai/decisions エンドポイントから判定結果を取得
resp=$(curl -sf "${API_URL}/ai/decisions?limit=100" 2>/dev/null || echo '{"items":[]}')

if echo "$resp" | python3 -c "import sys,json; data=json.load(sys.stdin); items=data.get('items',[]); total=len(items); buy=sum(1 for x in items if x.get('action')=='BUY'); sell=sum(1 for x in items if x.get('action')=='SELL'); hold=sum(1 for x in items if x.get('action')=='HOLD'); print(f'総件数: {total}'); print(f'BUY: {buy} ({100*buy//total if total else 0}%)'); print(f'SELL: {sell} ({100*sell//total if total else 0}%)'); print(f'HOLD: {hold} ({100*hold//total if total else 0}%)')" 2>/dev/null; then
  echo ""
  echo "✅ 分析完了"
else
  echo "⚠️ APIからデータ取得失敗 (エンドポイント未実装の可能性)"
  echo "   生レスポンス: $(echo $resp | head -c 200)"
fi
