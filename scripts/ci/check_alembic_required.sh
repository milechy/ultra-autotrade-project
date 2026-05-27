#!/usr/bin/env bash
# Ultra AutoTrade — Alembic migration 必須化 CI guard
#
# 目的:
#   backend/app/.../models.py または backend/app/models/ 配下が変更されたら、
#   同じ PR で backend/alembic/versions/ に新規 migration が追加されていることを必須化する。
#
#   Asana 1215151958676195 / [LAUNCH-GATE-B] schema drift 再発防止。
#
# 終了コード:
#   0: OK (models 変更なし / models と migration 両方変更あり)
#   1: FAIL (models 変更ありだが migration 追加なし)
#
# 補足:
#   - GITHUB_BASE_REF が無い場合は HEAD~1 で diff を取る（ローカル実行用）。
#   - 例外（コメントのみ変更など）は未実装。まず厳密に。誤検知が問題化したら例外追加。
set -euo pipefail

BASE_REF="${GITHUB_BASE_REF:-main}"

# CI 環境では origin を fetch する。ローカルでは失敗しても続行。
git fetch origin "${BASE_REF}" --depth=50 >/dev/null 2>&1 || true

if git rev-parse --verify "origin/${BASE_REF}" >/dev/null 2>&1; then
  CHANGED="$(git diff --name-only "origin/${BASE_REF}...HEAD" 2>/dev/null || true)"
else
  CHANGED="$(git diff --name-only "HEAD~1...HEAD" 2>/dev/null || true)"
fi

if [[ -z "${CHANGED}" ]]; then
  echo "ℹ️  変更ファイルが検出できませんでした (base=${BASE_REF})。skip 扱い。"
  exit 0
fi

# models 変更検出:
#   - backend/app/models/**/*.py (将来構造)
#   - backend/app/<module>/models.py (現行構造: users/portfolio/etc)
MODELS_CHANGED="$(echo "${CHANGED}" | grep -E '^backend/app/(models/.*|.*/models)\.py$' || true)"

# alembic versions/ への新規/変更追加検出
MIGRATIONS_ADDED="$(echo "${CHANGED}" | grep -E '^backend/alembic/versions/.*\.py$' || true)"

if [[ -n "${MODELS_CHANGED}" && -z "${MIGRATIONS_ADDED}" ]]; then
  echo "❌ FAIL: models/ に変更がありますが backend/alembic/versions/ に migration が追加されていません"
  echo ""
  echo "変更された models:"
  echo "${MODELS_CHANGED}" | sed 's/^/  - /'
  echo ""
  echo "対処:"
  echo "  cd backend && alembic revision --autogenerate -m 'describe schema change'"
  echo "  生成された backend/alembic/versions/<rev>.py を確認しコミットしてください。"
  echo ""
  echo "  どうしても migration 不要な場合 (例: docstring 変更のみ) は PR description に"
  echo "  '[skip-alembic-check]' を含め、レビュアー承認のもとマージしてください。"
  exit 1
fi

if [[ -n "${MODELS_CHANGED}" ]]; then
  echo "✅ models 変更 + migration 追加を検出。OK。"
  echo "変更 models: $(echo "${MODELS_CHANGED}" | wc -l) file(s)"
  echo "追加 migration: $(echo "${MIGRATIONS_ADDED}" | wc -l) file(s)"
else
  echo "✅ models 変更なし。skip。"
fi
