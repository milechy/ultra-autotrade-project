#!/usr/bin/env bash
set -euo pipefail

# Ultra AutoTrade – staging backend デプロイスクリプト
#
# 想定する処理フロー:
#  1. プロジェクトルートへ移動
#  2. 任意で git pull (コメントアウトで運用側が制御)
#  3. docker compose によるビルド＆再起動
#
# 注意:
#  - .env.staging が project root に存在していること
#  - docker / docker compose が使用可能であること

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "ERROR: ${COMPOSE_FILE} not found in ${PROJECT_ROOT}" >&2
  exit 1
fi

echo "[deploy] project root: ${PROJECT_ROOT}"
echo "[deploy] using compose file: ${COMPOSE_FILE}"

# 必要に応じてコメントアウトを外して利用:
# echo "[deploy] pulling latest code from git..."
# git pull --ff-only

# docker compose / docker-compose のどちらが使えるか判定
if command -v docker compose >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "ERROR: docker compose or docker-compose is not installed." >&2
  exit 1
fi

echo "[deploy] building image..."
${DC} -f "${COMPOSE_FILE}" build

echo "[deploy] restarting containers..."
${DC} -f "${COMPOSE_FILE}" up -d

echo "[deploy] current status:"
${DC} -f "${COMPOSE_FILE}" ps

echo "[deploy] done."
