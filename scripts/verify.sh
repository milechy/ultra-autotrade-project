#!/usr/bin/env bash
set -euo pipefail

START_TIME=$(date +%s)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================="
echo "  Ultra AutoTrade — DoD Verification"
echo "========================================="

step() {
  echo ""
  echo "--- $1 ---"
}

fail() {
  echo "❌ $1 FAILED"
  exit 1
}

# ── Backend ──────────────────────────────────

step "[1/7] ruff check"
if (cd "$PROJECT_ROOT/backend" && ruff check .); then
  echo "✅ ruff check passed"
else
  fail "ruff check"
fi

step "[2/7] ruff format --check"
if (cd "$PROJECT_ROOT/backend" && ruff format --check .); then
  echo "✅ ruff format passed"
else
  fail "ruff format"
fi

step "[3/7] mypy"
if (cd "$PROJECT_ROOT/backend" && mypy app/ --config-file ../pyproject.toml); then
  echo "✅ mypy passed"
else
  fail "mypy"
fi

step "[4/7] pytest + coverage 80%+"
if (cd "$PROJECT_ROOT/backend" && pytest tests/ --cov=app --cov-fail-under=80 -q --tb=short); then
  echo "✅ pytest passed (coverage >= 80%)"
else
  fail "pytest"
fi

step "[5/7] ruff security check"
if (cd "$PROJECT_ROOT/backend" && ruff check . --select S); then
  echo "✅ security check passed"
else
  echo "⚠️  security warnings found (review manually)"
  # セキュリティ警告は warning 扱い（終了しない）
fi

# ── Frontend ─────────────────────────────────

step "[6/7] tsc --noEmit"
if (cd "$PROJECT_ROOT/frontend" && npx tsc --noEmit); then
  echo "✅ tsc passed"
else
  fail "tsc"
fi

step "[7/7] npm run build"
# .next 競合防止のため並行実行禁止
if (cd "$PROJECT_ROOT/frontend" && npm run build); then
  echo "✅ build passed"
else
  fail "npm run build"
fi

# ── Summary ──────────────────────────────────

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "✅ All checks passed (${ELAPSED}s)"
echo "========================================="
