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
#   0: OK (models 変更なし / スキーマに影響しない変更のみ / models と migration 両方変更あり)
#   1: FAIL (スキーマに影響する models 変更ありだが migration 追加なし)
#
# 補足:
#   - GITHUB_BASE_REF が無い場合は HEAD~1 で diff を取る（ローカル実行用）。
#   - 2026-07-17: **スキーマ影響判定を追加**（当初の「例外は未実装。まず厳密に。誤検知が
#     問題化したら例外追加」という設計メモに従う）。ファイル名だけで判定していたため、
#     models.py 内の docstring / 定数 / ヘルパ関数の変更でも FAIL していた（PR #994 で顕在化:
#     `PHASE_1_ALLOWED_RISK_MODES` の env 化＝列定義ゼロの変更が落ちた）。
#     「赤いのが常態」は本物の schema drift を見逃す土壌になるため、誤検知の側を潰す。
#   - **判定は fail-closed**: 差分にスキーマ関連の字句が 1 つでもあれば従来どおり migration 必須。
#     コメント内の一致でも FAIL する（安全側）。判定に迷う余地を作らない。
set -euo pipefail

BASE_REF="${GITHUB_BASE_REF:-main}"

# CI 環境では origin を fetch する。ローカルでは失敗しても続行。
git fetch origin "${BASE_REF}" --depth=50 >/dev/null 2>&1 || true

if git rev-parse --verify "origin/${BASE_REF}" >/dev/null 2>&1; then
  DIFF_RANGE="origin/${BASE_REF}...HEAD"
else
  DIFF_RANGE="HEAD~1...HEAD"
fi

CHANGED="$(git diff --name-only "${DIFF_RANGE}" 2>/dev/null || true)"

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

if [[ -z "${MODELS_CHANGED}" ]]; then
  echo "✅ models 変更なし。skip。"
  exit 0
fi

if [[ -n "${MIGRATIONS_ADDED}" ]]; then
  echo "✅ models 変更 + migration 追加を検出。OK。"
  echo "変更 models: $(echo "${MODELS_CHANGED}" | wc -l | tr -d ' ') file(s)"
  echo "追加 migration: $(echo "${MIGRATIONS_ADDED}" | wc -l | tr -d ' ') file(s)"
  exit 0
fi

# --- migration が無い場合: スキーマに影響する変更かを判定する ---
#
# SQLAlchemy でテーブル定義に効く字句。1 つでも追加/削除行に現れたら「スキーマ変更の可能性
# あり」として従来どおり FAIL する（fail-closed）。
SCHEMA_PATTERN='mapped_column|Column\(|__tablename__|__table_args__|CheckConstraint|UniqueConstraint|PrimaryKeyConstraint|ForeignKey|Index\(|relationship\(|server_default|nullable=|primary_key|autoincrement|Mapped\[|ALTER TABLE|CREATE TABLE|DROP COLUMN|sa\.'

# shellcheck disable=SC2086 # MODELS_CHANGED は改行区切りのパス列（意図的に分割する）
SCHEMA_HITS="$(git diff "${DIFF_RANGE}" -- ${MODELS_CHANGED} 2>/dev/null \
  | grep -E '^[+-]' \
  | grep -vE '^(\+\+\+|---)' \
  | grep -E "${SCHEMA_PATTERN}" || true)"

if [[ -z "${SCHEMA_HITS}" ]]; then
  echo "✅ models 変更を検出しましたが、差分にスキーマ関連の変更はありません。skip。"
  echo ""
  echo "変更された models:"
  echo "${MODELS_CHANGED}" | sed 's/^/  - /'
  echo ""
  echo "判定根拠: 追加/削除行に以下のいずれも出現しませんでした:"
  echo "  ${SCHEMA_PATTERN}"
  echo ""
  echo "※ 誤ってスキーマ変更を見逃していると感じたら、この判定を疑ってください"
  echo "  (判定は fail-closed 設計: 上記字句が 1 つでもあれば FAIL します)。"
  exit 0
fi

echo "❌ FAIL: models/ にスキーマ関連の変更がありますが backend/alembic/versions/ に migration が追加されていません"
echo ""
echo "変更された models:"
echo "${MODELS_CHANGED}" | sed 's/^/  - /'
echo ""
echo "スキーマ関連と判定した差分行:"
echo "${SCHEMA_HITS}" | head -20 | sed 's/^/  /'
echo ""
echo "対処:"
echo "  backend/alembic/versions/ に migration を **手書きで** 追加してください。"
echo ""
echo "  ⚠️  本リポジトリでは 'alembic revision --autogenerate' は使用禁止です。"
echo "     alembic/env.py が全モデルを import しておらず Base.metadata が不完全なため、"
echo "     実在するテーブルへの DROP を誤生成します"
echo "     (memory: project_alembic_envpy_incomplete_model_imports)。"
echo ""
echo "  スキーマ変更でないのに検出された場合 (定数やコメントに上記字句が含まれる等) は、"
echo "  PR description に '[skip-alembic-check]' と根拠を明記し、レビュアー承認のもと"
echo "  マージしてください。"
exit 1
