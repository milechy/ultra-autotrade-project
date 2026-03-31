#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "  Ultra AutoTrade — DoD Verification"
echo "========================================="

FAIL=0

echo ""
echo "--- [1/5] ruff check ---"
if (cd backend && ruff check .); then
  echo "✅ ruff check passed"
else
  echo "❌ ruff check FAILED"
  FAIL=1
fi

echo ""
echo "--- [2/5] ruff format ---"
if (cd backend && ruff format --check .); then
  echo "✅ ruff format passed"
else
  echo "❌ ruff format FAILED"
  FAIL=1
fi

echo ""
echo "--- [3/5] mypy ---"
if (cd backend && mypy app/ --config-file ../pyproject.toml); then
  echo "✅ mypy passed"
else
  echo "❌ mypy FAILED"
  FAIL=1
fi

echo ""
echo "--- [4/5] pytest + coverage ---"
if (cd backend && pytest tests/ --cov=app --cov-fail-under=80 -q --tb=short); then
  echo "✅ pytest passed (coverage >= 80%)"
else
  echo "❌ pytest FAILED"
  FAIL=1
fi

echo ""
echo "--- [5/5] security check ---"
if (cd backend && ruff check . --select S); then
  echo "✅ security check passed"
else
  echo "⚠️  security warnings found (review manually)"
fi

echo ""
echo "========================================="
if [ "$FAIL" -eq 0 ]; then
  echo "✅ ALL CHECKS PASSED — ready to commit"
  exit 0
else
  echo "❌ SOME CHECKS FAILED — fix before committing"
  exit 1
fi
