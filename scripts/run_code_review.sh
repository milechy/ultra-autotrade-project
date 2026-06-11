#!/usr/bin/env bash
# scripts/run_code_review.sh — Alibaba Open Code Review (ocr) で PR diff を LLM レビュー
#
# 用途:
#   PR の git diff を Claude にレビューさせ、行レベルの指摘を生成する。
#   現行の手動 Gate 6 (/codex:review) を補完。backend/app/aave/ 変更時のセキュリティ検査を自動化。
#
# 使い方:
#   ./scripts/run_code_review.sh                       # origin/main..HEAD をレビュー
#   BASE=origin/dev ./scripts/run_code_review.sh        # base 変更
#   OUTPUT=review.json ./scripts/run_code_review.sh      # 出力先指定
#
# 必要な環境変数（CI では GitHub Secrets から渡す）:
#   ANTHROPIC_API_KEY   — Claude API キー（OCR_LLM_TOKEN にマップ）
#
# 参考: https://github.com/alibaba/open-code-review （Apache-2.0）
#   ocr は公式 GitHub Action 無し。npm グローバル install + CLI 実行 + JSON パースで使う。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BASE="${BASE:-origin/main}"
HEAD_REF="${HEAD_REF:-HEAD}"
OUTPUT="${OUTPUT:-/tmp/ocr-review.json}"

# ---- Anthropic 向け ocr 設定（環境変数経由 / config.json 不要）----
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY が未設定です（CI では Secrets から渡す）" >&2
  exit 2
fi
export OCR_USE_ANTHROPIC="true"
export OCR_LLM_URL="${OCR_LLM_URL:-https://api.anthropic.com}"
export OCR_LLM_TOKEN="$ANTHROPIC_API_KEY"
export OCR_LLM_MODEL="${OCR_LLM_MODEL:-claude-sonnet-4-6}"
export OCR_LLM_AUTH_HEADER="${OCR_LLM_AUTH_HEADER:-x-api-key}"

# ---- ocr の準備 ----
if ! command -v ocr >/dev/null 2>&1; then
  echo "ocr が無いため npm global install します..."
  npm install -g @alibaba-group/open-code-review
fi

# ---- レビュー対象の確認（aave 変更は必須レビュー）----
git fetch origin -q 2>/dev/null || true
CHANGED="$(git diff --name-only "$BASE"..."$HEAD_REF" 2>/dev/null || true)"
echo "=== 変更ファイル ==="
echo "$CHANGED"
if echo "$CHANGED" | grep -qE '^backend/app/aave/'; then
  echo "⚠ backend/app/aave/ の変更を含む — セキュリティ重点レビュー対象"
fi

# ---- 実行 ----
echo "=== ocr review: $BASE..$HEAD_REF ==="
ocr review --from "$BASE" --to "$HEAD_REF" --format json --output "$OUTPUT" || \
  ocr review --from "$BASE" --to "$HEAD_REF" --format json > "$OUTPUT" || true

if [[ -f "$OUTPUT" ]]; then
  echo "=== レビュー出力: $OUTPUT ==="
  if command -v jq >/dev/null 2>&1; then
    COUNT="$(jq -r '[.. | objects | select(.comment? // .message? // .body?)] | length' "$OUTPUT" 2>/dev/null || echo "?")"
    echo "指摘件数(目安): $COUNT"
  fi
else
  echo "ERROR: レビュー出力が生成されませんでした" >&2
  exit 1
fi
