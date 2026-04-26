#!/usr/bin/env bash
# check_frozen_files.sh
# pre-commit フックまたは手動実行で凍結ファイルの変更を検出する。
# CI (.github/workflows/path-check.yml) と同じ FROZEN_PATTERNS を使用。
#
# Usage:
#   ./scripts/check_frozen_files.sh          # staged ファイルを検査
#   ./scripts/check_frozen_files.sh --all    # HEAD と比較して全変更を検査

set -euo pipefail

FROZEN_PATTERNS=(
  "backend/app/shared/"
  "backend/app/main.py"
  "backend/app/database.py"
  "backend/conftest.py"
  "backend/requirements.txt"
  "backend/alembic/versions/"
  ".github/workflows/path-check.yml"
  ".github/workflows/env-separation-check.yml"
  "pyproject.toml"
)

# staged ファイル or 全変更ファイルを取得
if [ "${1:-}" = "--all" ]; then
  CHANGED=$(git diff --name-only HEAD 2>/dev/null || true)
else
  CHANGED=$(git diff --cached --name-only 2>/dev/null || true)
fi

if [ -z "$CHANGED" ]; then
  exit 0
fi

# docs/integration/backend_deps.md が変更に含まれていれば「申請済み」とみなす
HAS_BACKEND_DEPS_UPDATE=0
if echo "$CHANGED" | grep -q '^docs/integration/backend_deps\.md$'; then
  HAS_BACKEND_DEPS_UPDATE=1
fi

VIOLATIONS=""
WARNINGS=""

while IFS= read -r file; do
  [ -z "$file" ] && continue

  for pattern in "${FROZEN_PATTERNS[@]}"; do
    if echo "$file" | grep -q "^$pattern"; then
      if [ "$HAS_BACKEND_DEPS_UPDATE" -eq "1" ]; then
        WARNINGS="${WARNINGS}  ⚠️  凍結ファイル変更（申請済み）: ${file}\n"
      else
        VIOLATIONS="${VIOLATIONS}  ❌ 凍結ファイル変更（未申請）: ${file}\n"
      fi
      break
    fi
  done
done <<< "$CHANGED"

if [ -n "$WARNINGS" ]; then
  echo ""
  echo "🛡️  凍結ファイルガード — 警告"
  echo "──────────────────────────────────────────────"
  echo -e "$WARNINGS"
  echo "  docs/integration/backend_deps.md に申請済みのため続行します。"
fi

if [ -n "$VIOLATIONS" ]; then
  echo ""
  echo "🛡️  凍結ファイルガード — 違反"
  echo "──────────────────────────────────────────────"
  echo -e "$VIOLATIONS"
  echo "  解決方法:"
  echo "    1. docs/integration/backend_deps.md の凍結ファイル登録表で解凍条件を確認"
  echo "    2. 同ファイルに「変更 #N」エントリを追加して git add"
  echo "    3. 再度 git commit を実行"
  echo ""
  exit 1
fi

exit 0
