#!/bin/bash
# check_next_public_sync.sh
# frontend/Dockerfile の ARG/ENV と docker-compose.staging.yml の build.args が
# 同期されているか確認する。
# 欠けがあると NEXT_PUBLIC_* が http:// fallback 値でビルドされ Mixed Content エラーになる
# （2026-04-03 iPhone インシデントより）。
#
# 使い方:
#   bash scripts/check_next_public_sync.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DOCKERFILE="${PROJECT_ROOT}/frontend/Dockerfile"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.staging.yml"
ENV_FILE="${PROJECT_ROOT}/.env.staging"

ERRORS=0

if [ ! -f "${DOCKERFILE}" ]; then
  echo "⚠️  WARNING: ${DOCKERFILE} が見つかりません"
  exit 1
fi

if [ ! -f "${COMPOSE_FILE}" ]; then
  echo "⚠️  WARNING: ${COMPOSE_FILE} が見つかりません"
  exit 1
fi

# Dockerfile の ARG/ENV から NEXT_PUBLIC_* を抽出
DOCKERFILE_VARS=$(grep -E "^ARG NEXT_PUBLIC_|^ENV NEXT_PUBLIC_" "${DOCKERFILE}" \
  | sed 's/^ARG //' | sed 's/^ENV //' | cut -d= -f1 | sort || true)

# docker-compose.staging.yml の build.args から NEXT_PUBLIC_* を抽出
COMPOSE_VARS=$(grep -E "NEXT_PUBLIC_" "${COMPOSE_FILE}" \
  | grep -v "#" \
  | sed 's/.*NEXT_PUBLIC_/NEXT_PUBLIC_/' | cut -d= -f1 | cut -d: -f1 | sort -u || true)

if [ -z "${DOCKERFILE_VARS}" ]; then
  echo "⚠️  WARNING: Dockerfile に NEXT_PUBLIC_* の ARG/ENV が見つかりません"
  ERRORS=$((ERRORS + 1))
fi

echo "Dockerfile NEXT_PUBLIC_* vars:"
echo "${DOCKERFILE_VARS:-（なし）}"
echo ""
echo "docker-compose.staging.yml NEXT_PUBLIC_* vars:"
echo "${COMPOSE_VARS:-（なし）}"
echo ""

# Dockerfile にあって compose にないもの
MISSING_IN_COMPOSE=$(comm -23 \
  <(echo "${DOCKERFILE_VARS}") \
  <(echo "${COMPOSE_VARS}") || true)

if [ -n "${MISSING_IN_COMPOSE}" ]; then
  echo "⚠️  WARNING: Dockerfile に ARG があるが docker-compose.staging.yml の build.args にない変数:"
  echo "${MISSING_IN_COMPOSE}"
  echo "  → docker-compose.staging.yml の frontend.build.args に追加してください"
  ERRORS=$((ERRORS + 1))
fi

# .env.staging に値が設定されているか確認
if [ -f "${ENV_FILE}" ]; then
  for VAR in ${DOCKERFILE_VARS}; do
    if ! grep -q "^${VAR}=" "${ENV_FILE}" 2>/dev/null; then
      echo "⚠️  WARNING: ${VAR} が .env.staging に未設定です"
      ERRORS=$((ERRORS + 1))
    fi
  done
fi

if [ "${ERRORS}" -gt 0 ]; then
  echo ""
  echo "⚠️  NEXT_PUBLIC_* 同期チェック: ${ERRORS} 件の問題が見つかりました"
  echo "  → 不足変数を追加後、docker compose build --no-cache frontend を実行してください"
  exit 1
fi

echo "✅ NEXT_PUBLIC_* 変数の同期に問題はありません"
