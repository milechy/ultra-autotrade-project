#!/bin/bash
# check_next_public_sync.sh
# NEXT_PUBLIC_* 変数が frontend ソースコード・Dockerfile ARG・docker-compose build.args に
# 揃っているか確認する。揃っていないと Mixed Content / undefined 埋め込みの原因になる。
# （2026-04-03 iPhone Mixed Content インシデントより）
#
# 使い方:
#   bash scripts/check_next_public_sync.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

DOCKERFILE="${FRONTEND_DIR}/Dockerfile"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.staging.yml"

ERRORS=0

if [ ! -f "${DOCKERFILE}" ]; then
  echo "ERROR: ${DOCKERFILE} が見つかりません"
  exit 1
fi

if [ ! -f "${COMPOSE_FILE}" ]; then
  echo "ERROR: ${COMPOSE_FILE} が見つかりません"
  exit 1
fi

# Rule 5: frontend ソースコードで使われている NEXT_PUBLIC_ 変数を抽出
SRC_DIRS=("${FRONTEND_DIR}/app" "${FRONTEND_DIR}/components" "${FRONTEND_DIR}/hooks" "${FRONTEND_DIR}/lib")
EXISTING_DIRS=()
for dir in "${SRC_DIRS[@]}"; do
  [ -d "$dir" ] && EXISTING_DIRS+=("$dir")
done

USED_VARS=""
if [ ${#EXISTING_DIRS[@]} -gt 0 ]; then
  USED_VARS=$(grep -roh 'NEXT_PUBLIC_[A-Z_]*' "${EXISTING_DIRS[@]}" \
    --include="*.ts" --include="*.tsx" 2>/dev/null | sort -u || true)
fi

# Dockerfile の ARG から NEXT_PUBLIC_* を抽出
DOCKERFILE_ARGS=$(grep -E "^ARG NEXT_PUBLIC_" "${DOCKERFILE}" \
  | sed 's/^ARG //' | sort || true)

# docker-compose.staging.yml の build.args セクションから NEXT_PUBLIC_* を抽出
# (frontend が最終サービスのため awk range は使わず grep で全体から抽出)
COMPOSE_BUILD_VARS=$(grep -oE 'NEXT_PUBLIC_[A-Z_]+' "${COMPOSE_FILE}" | sort -u || true)

echo "=== Rule 5: ソースコード → Dockerfile ARG チェック ==="
if [ -z "${USED_VARS}" ]; then
  echo "WARN: NEXT_PUBLIC_ 変数がソースコード内で見つかりませんでした（パスを確認してください）"
else
  for VAR in $USED_VARS; do
    if ! echo "${DOCKERFILE_ARGS}" | grep -q "^${VAR}$"; then
      echo "ERROR: ${VAR} はソースコードで使用されているが ${DOCKERFILE} に ARG 定義がありません"
      ERRORS=$((ERRORS + 1))
    fi
  done
  echo "チェック対象: $(echo "$USED_VARS" | wc -w | tr -d ' ') 変数"
fi

echo ""
echo "=== Rule 5: ソースコード → docker-compose build.args チェック ==="
if [ -n "${USED_VARS}" ]; then
  for VAR in $USED_VARS; do
    if ! echo "${COMPOSE_BUILD_VARS}" | grep -q "^${VAR}$"; then
      echo "ERROR: ${VAR} はソースコードで使用されているが ${COMPOSE_FILE} の frontend build.args に定義がありません"
      ERRORS=$((ERRORS + 1))
    fi
  done
fi

echo ""
echo "=== Dockerfile ARG → docker-compose build.args 整合チェック ==="
for VAR in $DOCKERFILE_ARGS; do
  if ! echo "${COMPOSE_BUILD_VARS}" | grep -q "^${VAR}$"; then
    echo "WARN: ${VAR} は Dockerfile ARG にあるが docker-compose.staging.yml の build.args にありません"
  fi
done

echo ""
echo "=== Rule 6: messages/ COPY チェック（next-intl standalone 必須）==="
if ! grep -q "COPY.*messages" "${DOCKERFILE}"; then
  echo "ERROR: ${DOCKERFILE} に messages/ の COPY がありません（next-intl standalone で翻訳が消えます）"
  ERRORS=$((ERRORS + 1))
else
  echo "OK: messages/ COPY が Dockerfile に存在します"
fi

echo ""
if [ "${ERRORS}" -gt 0 ]; then
  echo "FAIL: ${ERRORS} 件の同期エラーが見つかりました"
  echo "修正方法: frontend/Dockerfile に ARG/ENV を追加し、docker-compose.staging.yml の frontend build.args にも追加後、"
  echo "         docker compose -f docker-compose.staging.yml build --no-cache frontend を実行してください"
  exit 1
fi

echo "OK: 全 NEXT_PUBLIC_ 変数が Dockerfile ARG + docker-compose build.args に同期されています"
