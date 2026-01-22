#!/usr/bin/env bash
# scripts/deploy_production_backend.sh
#
# Ultra AutoTrade Backend を production 環境にデプロイするための標準スクリプト。
# 想定:
# - リポジトリ: /opt/ultra-autotrade
# - backend:   /opt/ultra-autotrade/backend
# - env:       /opt/ultra-autotrade/backend/.env.production
# - compose:   /opt/ultra-autotrade/docker-compose.production.yml
#
# ※ 上記パスは環境に応じて調整してよい。
#   調整した場合は docs/16_infra_deployment_guide.md も更新すること。

set -euo pipefail

REPO_DIR="/opt/ultra-autotrade"
BACKEND_DIR="${REPO_DIR}/backend"
ENV_FILE="${BACKEND_DIR}/.env.production"
COMPOSE_FILE="${REPO_DIR}/docker-compose.production.yml"
SERVICE_NAME="ultra-autotrade-backend-production"

log() {
  # シンプルなログ出力関数
  echo "[deploy][$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
  echo "[deploy][ERROR] $*" >&2
  exit 1
}

log "Ultra AutoTrade backend production deploy 開始"

# 1. リポジトリ確認
if [[ ! -d "${REPO_DIR}" ]]; then
  error "REPO_DIR=${REPO_DIR} が存在しません。パスを確認してください。"
fi

if [[ ! -d "${REPO_DIR}/.git" ]]; then
  error "REPO_DIR=${REPO_DIR} は Git リポジトリではありません。"
fi

cd "${REPO_DIR}"

# 2. 最新コード取得
log "Git リポジトリを更新します（git pull --ff-only）"
git pull --ff-only || error "git pull に失敗しました。"

# 3. 必須ファイルの存在確認
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  error "docker-compose.production.yml が見つかりません: ${COMPOSE_FILE}"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  error ".env.production が見つかりません: ${ENV_FILE}"
fi

# 4. backend イメージビルド & コンテナ起動
log "docker compose で backend イメージをビルドします"
docker compose -f "${COMPOSE_FILE}" build backend || error "backend のビルドに失敗しました。"

log "docker compose で backend コンテナを再起動します (up -d)"
docker compose -f "${COMPOSE_FILE}" up -d backend || error "backend コンテナの起動に失敗しました。"

# 5. 状態確認
log "backend コンテナの状態を確認します"
docker compose -f "${COMPOSE_FILE}" ps backend || log "docker compose ps backend の実行に失敗しました（致命的ではありません）"

log "Ultra AutoTrade backend production deploy 完了"

実行権限付与例

chmod +x scripts/deploy_production_backend.sh

実行例

sudo ./scripts/deploy_production_backend.sh

※ このスクリプトは docker-compose 運用前提 です。
systemd で運用する場合は、Git 更新 → venv 再インストール →
sudo systemctl restart ultra-autotrade-backend-production を
手順として docs 側に書く想定です。