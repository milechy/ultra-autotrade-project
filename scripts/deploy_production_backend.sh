#!/usr/bin/env bash
# scripts/deploy_production_backend.sh
#
# Ultra AutoTrade Backend を production 環境にデプロイするための標準スクリプト。
#
# 機能:
# - Git pull --ff-only（fast-forward のみ）
# - Docker build
# - Docker compose up -d
# - ヘルスチェック
# - エラー時の自動ロールバック
#
# 想定:
# - リポジトリ: /opt/ultra-autotrade
# - backend:   /opt/ultra-autotrade/backend
# - env:       /opt/ultra-autotrade/backend/.env.production
# - compose:   /opt/ultra-autotrade/docker-compose.production.yml
#
# ※ 上記パスは環境に応じて調整してよい。
#   調整した場合は docs/16_infra_deployment_guide.md も更新すること。

set -euo pipefail

# =============================================================================
# 設定
# =============================================================================
REPO_DIR="${REPO_DIR:-/opt/ultra-autotrade}"
BACKEND_DIR="${REPO_DIR}/backend"
ENV_FILE="${BACKEND_DIR}/.env.production"
COMPOSE_FILE="${REPO_DIR}/docker-compose.production.yml"
SERVICE_NAME="backend"
HEALTH_CHECK_URL="${HEALTH_CHECK_URL:-http://localhost:8000/health}"
HEALTH_CHECK_RETRIES="${HEALTH_CHECK_RETRIES:-10}"
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-5}"
PREVIOUS_COMMIT=""
ROLLBACK_ENABLED="${ROLLBACK_ENABLED:-true}"

# =============================================================================
# ユーティリティ関数
# =============================================================================
log() {
    echo "[deploy][$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

warn() {
    echo "[deploy][WARN][$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

error() {
    echo "[deploy][ERROR][$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

die() {
    error "$*"
    exit 1
}

# docker compose コマンドを判定
get_docker_compose_cmd() {
    if command -v docker compose >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        die "docker compose or docker-compose is not installed."
    fi
}

DC=$(get_docker_compose_cmd)

# =============================================================================
# ヘルスチェック
# =============================================================================
health_check() {
    local url="$1"
    local retries="$2"
    local interval="$3"
    local attempt=1

    log "ヘルスチェックを開始します: ${url}"

    while [[ ${attempt} -le ${retries} ]]; do
        log "ヘルスチェック試行 ${attempt}/${retries}..."

        if curl -sf -o /dev/null --connect-timeout 5 --max-time 10 "${url}"; then
            log "ヘルスチェック成功"
            return 0
        fi

        if [[ ${attempt} -lt ${retries} ]]; then
            log "ヘルスチェック失敗、${interval}秒後にリトライ..."
            sleep "${interval}"
        fi

        ((attempt++))
    done

    error "ヘルスチェック失敗（${retries}回試行）"
    return 1
}

# =============================================================================
# ロールバック
# =============================================================================
rollback() {
    local commit="$1"

    if [[ "${ROLLBACK_ENABLED}" != "true" ]]; then
        warn "ROLLBACK_ENABLED=false のためロールバックをスキップします"
        return 1
    fi

    if [[ -z "${commit}" ]]; then
        error "ロールバック先のコミットが不明です"
        return 1
    fi

    log "ロールバックを開始します: ${commit}"

    cd "${REPO_DIR}"

    # Git を前のコミットに戻す
    if ! git checkout "${commit}"; then
        error "git checkout ${commit} に失敗しました"
        return 1
    fi

    # 再ビルド & 再起動
    log "ロールバック用にイメージを再ビルドします"
    if ! ${DC} -f "${COMPOSE_FILE}" build "${SERVICE_NAME}"; then
        error "ロールバック時のビルドに失敗しました"
        return 1
    fi

    log "ロールバック用にコンテナを再起動します"
    if ! ${DC} -f "${COMPOSE_FILE}" up -d "${SERVICE_NAME}"; then
        error "ロールバック時のコンテナ起動に失敗しました"
        return 1
    fi

    log "ロールバック完了: ${commit}"
    return 0
}

# =============================================================================
# メイン処理
# =============================================================================
main() {
    log "=========================================="
    log "Ultra AutoTrade backend production deploy"
    log "=========================================="

    # 1. リポジトリ確認
    log "Step 1: リポジトリ確認"
    if [[ ! -d "${REPO_DIR}" ]]; then
        die "REPO_DIR=${REPO_DIR} が存在しません。パスを確認してください。"
    fi

    if [[ ! -d "${REPO_DIR}/.git" ]]; then
        die "REPO_DIR=${REPO_DIR} は Git リポジトリではありません。"
    fi

    cd "${REPO_DIR}"

    # 現在のコミットを保存（ロールバック用）
    PREVIOUS_COMMIT=$(git rev-parse HEAD)
    log "現在のコミット: ${PREVIOUS_COMMIT}"

    # 2. 最新コード取得
    log "Step 2: Git リポジトリを更新（git pull --ff-only）"
    if ! git pull --ff-only; then
        die "git pull に失敗しました。ローカルの変更がある可能性があります。"
    fi

    NEW_COMMIT=$(git rev-parse HEAD)
    log "更新後のコミット: ${NEW_COMMIT}"

    if [[ "${PREVIOUS_COMMIT}" == "${NEW_COMMIT}" ]]; then
        log "コードに変更はありません。デプロイを続行します。"
    fi

    # 3. 必須ファイルの存在確認
    log "Step 3: 必須ファイル確認"
    if [[ ! -f "${COMPOSE_FILE}" ]]; then
        die "docker-compose.production.yml が見つかりません: ${COMPOSE_FILE}"
    fi

    if [[ ! -f "${ENV_FILE}" ]]; then
        die ".env.production が見つかりません: ${ENV_FILE}"
    fi

    log "必須ファイル確認完了"

    # 4. backend イメージビルド
    log "Step 4: Docker イメージビルド"
    if ! ${DC} -f "${COMPOSE_FILE}" build "${SERVICE_NAME}"; then
        die "backend のビルドに失敗しました。"
    fi

    # 5. コンテナ起動
    log "Step 5: コンテナ起動"
    if ! ${DC} -f "${COMPOSE_FILE}" up -d "${SERVICE_NAME}"; then
        error "backend コンテナの起動に失敗しました。"

        # ロールバック試行
        if rollback "${PREVIOUS_COMMIT}"; then
            die "デプロイ失敗。ロールバック完了。"
        else
            die "デプロイ失敗。ロールバックも失敗。手動対応が必要です。"
        fi
    fi

    # 6. ヘルスチェック
    log "Step 6: ヘルスチェック"
    sleep 3  # コンテナ起動を待機

    if ! health_check "${HEALTH_CHECK_URL}" "${HEALTH_CHECK_RETRIES}" "${HEALTH_CHECK_INTERVAL}"; then
        error "ヘルスチェック失敗。ロールバックを開始します。"

        # ロールバック試行
        if rollback "${PREVIOUS_COMMIT}"; then
            # ロールバック後のヘルスチェック
            sleep 5
            if health_check "${HEALTH_CHECK_URL}" 5 3; then
                die "デプロイ失敗。ロールバック完了、サービス復旧。"
            else
                die "デプロイ失敗。ロールバック完了、ただしヘルスチェックは失敗。手動確認が必要です。"
            fi
        else
            die "デプロイ失敗。ロールバックも失敗。手動対応が必要です。"
        fi
    fi

    # 7. 状態確認
    log "Step 7: 最終状態確認"
    ${DC} -f "${COMPOSE_FILE}" ps "${SERVICE_NAME}" || warn "docker compose ps の実行に失敗"

    log "=========================================="
    log "デプロイ完了"
    log "コミット: ${NEW_COMMIT}"
    log "=========================================="
}

# スクリプト実行
main "$@"