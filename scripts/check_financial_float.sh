#!/bin/bash
# check_financial_float.sh
# Aave / exchange / ai / protocols モジュールで float() を使った金額計算を検出する。
# Financial 計算には Decimal 型を使うこと（CLAUDE.md セキュリティルール）。
#
# 使い方:
#   bash scripts/check_financial_float.sh
#
# 意図的に float() を使う行には末尾に '# float OK' コメントを付けることで除外できる。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DIRS=(
  "backend/app/aave"
  "backend/app/exchange"
  "backend/app/ai"
  "backend/app/protocols"
)

ERRORS=0

for DIR in "${DIRS[@]}"; do
  FULL_DIR="${PROJECT_ROOT}/${DIR}"
  if [ ! -d "${FULL_DIR}" ]; then
    continue
  fi

  # float() の使用を検出（テストファイル・キャッシュ・# float OK 行は除外）
  FLOATS=$(grep -rn "float(" "${FULL_DIR}" \
    --include="*.py" \
    | grep -v "__pycache__" \
    | grep -v "test_" \
    | grep -v "# float OK" \
    || true)

  if [ -n "${FLOATS}" ]; then
    echo "WARNING: ${DIR} で float() が使用されています（Decimal 推奨）:"
    echo "${FLOATS}"
    echo ""
    ERRORS=$((ERRORS + 1))
  fi
done

if [ "${ERRORS}" -gt 0 ]; then
  echo "⚠️  ${ERRORS} ディレクトリで float() が検出されました"
  echo "  → Financial 計算には Decimal('...') を使用してください"
  echo "  → 意図的な使用は行末に '# float OK' コメントを追加してください"
  exit 1
fi

echo "✅ Financial モジュールに float() の使用はありません"
