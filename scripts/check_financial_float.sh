#!/bin/bash
# check_financial_float.sh
# Aave / exchange / ai / protocols モジュールで float() を使った金額計算を検出する。
# Financial 計算には Decimal 型を使うこと（CLAUDE.md セキュリティルール）。
#
# 使い方:
#   bash scripts/check_financial_float.sh
#
# 承認済みの float() 使用箇所は scripts/float_allowlist.txt で管理する。
# （以前の '# float OK' コメント方式は廃止）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ALLOWLIST="${SCRIPT_DIR}/float_allowlist.txt"

# STRICT ディレクトリ: float() が見つかったら exit 1
STRICT_DIRS=(
  "backend/app/aave"
  "backend/app/protocols/risk"
  "backend/app/ai"
)

# WARNING ディレクトリ: float() が見つかっても exit 0（警告のみ）
WARN_DIRS=(
  "backend/app/exchange"
  "backend/app/protocols/lido"
  "backend/app/protocols/pendle"
)

# allowlist から承認済みファイルパスを読み込む（コメント行・空行を除く）
ALLOWED_FILES=()
if [ -f "${ALLOWLIST}" ]; then
  while IFS= read -r line; do
    # コメント行・空行をスキップ
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// /}" ]] && continue
    # "path/to/file.py:LINENO — reason" または "path/to/file.py — reason" の形式
    FILE_PATH=$(echo "$line" | sed 's/:.*//' | sed 's/ —.*//' | xargs)
    if [ -n "$FILE_PATH" ]; then
      ALLOWED_FILES+=("$FILE_PATH")
    fi
  done < "${ALLOWLIST}"
fi

# ファイルパスが allowlist に含まれているか確認する関数
is_allowed() {
  local file_rel="$1"
  for allowed in "${ALLOWED_FILES[@]}"; do
    # 前方一致（ファイル単位 or ディレクトリ単位）
    if [[ "$file_rel" == "$allowed" || "$file_rel" == ${allowed}* ]]; then
      return 0
    fi
  done
  return 1
}

STRICT_ERRORS=0
WARN_COUNT=0

# --- STRICT チェック ---
for DIR in "${STRICT_DIRS[@]}"; do
  FULL_DIR="${PROJECT_ROOT}/${DIR}"
  [ -d "${FULL_DIR}" ] || continue

  while IFS= read -r match_line; do
    [ -z "$match_line" ] && continue
    # match_line 形式: /abs/path/to/file.py:NN:...
    ABS_FILE=$(echo "$match_line" | cut -d: -f1)
    REL_FILE="${ABS_FILE#${PROJECT_ROOT}/}"

    if ! is_allowed "$REL_FILE"; then
      echo "ERROR [STRICT]: float() in ${REL_FILE}"
      echo "  ${match_line}"
      STRICT_ERRORS=$((STRICT_ERRORS + 1))
    fi
  done < <(grep -rn "float(" "${FULL_DIR}" \
    --include="*.py" \
    | grep -v "__pycache__" \
    | grep -v "/test_" \
    || true)
done

# --- WARNING チェック ---
for DIR in "${WARN_DIRS[@]}"; do
  FULL_DIR="${PROJECT_ROOT}/${DIR}"
  [ -d "${FULL_DIR}" ] || continue

  while IFS= read -r match_line; do
    [ -z "$match_line" ] && continue
    ABS_FILE=$(echo "$match_line" | cut -d: -f1)
    REL_FILE="${ABS_FILE#${PROJECT_ROOT}/}"

    if ! is_allowed "$REL_FILE"; then
      echo "WARNING: float() in ${REL_FILE} (not in allowlist — consider Decimal)"
      echo "  ${match_line}"
      WARN_COUNT=$((WARN_COUNT + 1))
    fi
  done < <(grep -rn "float(" "${FULL_DIR}" \
    --include="*.py" \
    | grep -v "__pycache__" \
    | grep -v "/test_" \
    || true)
done

# --- 結果サマリー ---
if [ "${STRICT_ERRORS}" -gt 0 ]; then
  echo ""
  echo "❌ ${STRICT_ERRORS} unapproved float() usage(s) in STRICT directories (aave/, protocols/risk/, ai/)"
  echo "  → Financial 計算には Decimal('...') を使用してください"
  echo "  → ログ・表示のみの用途なら scripts/float_allowlist.txt に追記してください"
  exit 1
fi

if [ "${WARN_COUNT}" -gt 0 ]; then
  echo ""
  echo "⚠️  ${WARN_COUNT} unapproved float() usage(s) in WARNING directories (exchange/, protocols/lido/, protocols/pendle/)"
  echo "  → 問題ない場合は scripts/float_allowlist.txt に追記してください"
fi

echo "✅ Financial モジュールの float() チェック完了 (strict errors: 0, warnings: ${WARN_COUNT})"
