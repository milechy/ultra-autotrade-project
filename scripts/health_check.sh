#!/usr/bin/env bash
# scripts/health_check.sh
#
# Ultra AutoTrade ヘルスチェックスクリプト
#
# 機能:
# - /health エンドポイント確認
# - MonitoringService ステータス確認
# - Aave 接続確認
#
# 終了コード:
# - 0: 全てのチェックが成功
# - 1: いずれかのチェックが失敗
#
# 使用例:
#   ./scripts/health_check.sh                    # フルチェック
#   ./scripts/health_check.sh --endpoint-only    # エンドポイントのみ
#   ./scripts/health_check.sh --env-only         # 環境変数のみ
#   ./scripts/health_check.sh --connectivity     # 接続テストのみ
#   ./scripts/health_check.sh --full             # フルチェック（デフォルト）

set -uo pipefail

# =============================================================================
# 設定
# =============================================================================
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
STATUS_URL="${STATUS_URL:-http://localhost:8000/api/automation/status}"
AAVE_STATUS_URL="${AAVE_STATUS_URL:-http://localhost:8000/api/aave/status}"
TIMEOUT="${TIMEOUT:-10}"
VERBOSE="${VERBOSE:-false}"

# 必須環境変数リスト（production）
REQUIRED_ENV_VARS=(
    "AAVE_RPC_URL"
    "AAVE_WALLET_PRIVATE_KEY"
    "AAVE_POOL_ADDRESS"
    "AAVE_USDC_ADDRESS"
)

# カラー出力（TTY の場合のみ）
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

# =============================================================================
# ユーティリティ関数
# =============================================================================
log_info() {
    echo -e "[INFO] $*"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $*"
}

log_verbose() {
    if [[ "${VERBOSE}" == "true" ]]; then
        echo -e "[DEBUG] $*"
    fi
}

# =============================================================================
# チェック関数
# =============================================================================

# /health エンドポイントチェック
check_health_endpoint() {
    log_info "Checking /health endpoint: ${HEALTH_URL}"

    local response
    local http_code

    response=$(curl -sf --connect-timeout "${TIMEOUT}" --max-time "${TIMEOUT}" \
        -w "\n%{http_code}" "${HEALTH_URL}" 2>/dev/null)

    if [[ $? -ne 0 ]]; then
        log_error "/health endpoint is not responding"
        return 1
    fi

    http_code=$(echo "${response}" | tail -n1)
    local body
    body=$(echo "${response}" | sed '$d')

    if [[ "${http_code}" != "200" ]]; then
        log_error "/health returned HTTP ${http_code}"
        return 1
    fi

    log_success "/health endpoint is healthy (HTTP 200)"
    log_verbose "Response: ${body}"
    return 0
}

# MonitoringService ステータスチェック
check_monitoring_status() {
    log_info "Checking MonitoringService status: ${STATUS_URL}"

    local response
    local http_code

    response=$(curl -sf --connect-timeout "${TIMEOUT}" --max-time "${TIMEOUT}" \
        -w "\n%{http_code}" "${STATUS_URL}" 2>/dev/null)

    if [[ $? -ne 0 ]]; then
        log_warning "MonitoringService status endpoint not responding (may not be implemented)"
        return 0  # 警告のみ、失敗とはしない
    fi

    http_code=$(echo "${response}" | tail -n1)
    local body
    body=$(echo "${response}" | sed '$d')

    if [[ "${http_code}" != "200" ]]; then
        log_warning "MonitoringService status returned HTTP ${http_code}"
        return 0  # 警告のみ
    fi

    # JSON からトレーディング状態を抽出（jq がある場合）
    if command -v jq >/dev/null 2>&1; then
        local is_paused
        is_paused=$(echo "${body}" | jq -r '.is_trading_paused // false' 2>/dev/null)

        if [[ "${is_paused}" == "true" ]]; then
            log_warning "Trading is PAUSED (emergency stop may be active)"
        else
            log_success "MonitoringService is operational, trading allowed"
        fi

        local emergency_reason
        emergency_reason=$(echo "${body}" | jq -r '.emergency_reason // null' 2>/dev/null)
        if [[ "${emergency_reason}" != "null" && -n "${emergency_reason}" ]]; then
            log_warning "Emergency reason: ${emergency_reason}"
        fi
    else
        log_success "MonitoringService status endpoint is responding"
    fi

    log_verbose "Response: ${body}"
    return 0
}

# Aave 接続チェック
check_aave_connection() {
    log_info "Checking Aave connection: ${AAVE_STATUS_URL}"

    local response
    local http_code

    response=$(curl -sf --connect-timeout "${TIMEOUT}" --max-time "${TIMEOUT}" \
        -w "\n%{http_code}" "${AAVE_STATUS_URL}" 2>/dev/null)

    if [[ $? -ne 0 ]]; then
        log_warning "Aave status endpoint not responding (may not be implemented)"
        return 0  # 警告のみ
    fi

    http_code=$(echo "${response}" | tail -n1)
    local body
    body=$(echo "${response}" | sed '$d')

    if [[ "${http_code}" != "200" ]]; then
        log_warning "Aave status returned HTTP ${http_code}"
        return 0  # 警告のみ
    fi

    # JSON からヘルスファクターを抽出（jq がある場合）
    if command -v jq >/dev/null 2>&1; then
        local health_factor
        health_factor=$(echo "${body}" | jq -r '.health_factor // null' 2>/dev/null)

        if [[ "${health_factor}" != "null" && -n "${health_factor}" ]]; then
            log_success "Aave connection OK, Health Factor: ${health_factor}"
        else
            log_success "Aave connection OK (no position or HF not available)"
        fi
    else
        log_success "Aave status endpoint is responding"
    fi

    log_verbose "Response: ${body}"
    return 0
}

# 環境変数チェック
check_environment_variables() {
    log_info "Checking required environment variables"

    local missing=0

    for var in "${REQUIRED_ENV_VARS[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Missing required environment variable: ${var}"
            ((missing++))
        else
            # 秘密鍵は値を隠す
            if [[ "${var}" == *"KEY"* || "${var}" == *"SECRET"* || "${var}" == *"TOKEN"* ]]; then
                log_success "${var} is set (value hidden)"
            else
                log_verbose "${var}=${!var}"
                log_success "${var} is set"
            fi
        fi
    done

    if [[ ${missing} -gt 0 ]]; then
        log_error "${missing} required environment variable(s) missing"
        return 1
    fi

    log_success "All required environment variables are set"
    return 0
}

# state.json チェック
check_state_file() {
    local state_file="${AAVE_STATE_FILE_PATH:-/var/run/ultra/state.json}"

    log_info "Checking state file: ${state_file}"

    if [[ ! -f "${state_file}" ]]; then
        log_warning "State file does not exist: ${state_file}"
        return 0  # 初回起動時は存在しない可能性がある
    fi

    if [[ ! -r "${state_file}" ]]; then
        log_error "State file is not readable: ${state_file}"
        return 1
    fi

    # JSON 構文チェック（jq がある場合）
    if command -v jq >/dev/null 2>&1; then
        if ! jq empty "${state_file}" 2>/dev/null; then
            log_error "State file is not valid JSON"
            return 1
        fi

        local emergency_stop
        emergency_stop=$(jq -r '.emergency_stop // false' "${state_file}" 2>/dev/null)

        if [[ "${emergency_stop}" == "true" ]]; then
            log_warning "Emergency stop is ACTIVE in state.json"
        fi

        local circuit_closed
        circuit_closed=$(jq -r '.circuit_closed // false' "${state_file}" 2>/dev/null)

        if [[ "${circuit_closed}" == "true" ]]; then
            log_warning "Circuit breaker is CLOSED in state.json"
        fi

        log_success "State file is valid"
    else
        log_success "State file exists (jq not available for validation)"
    fi

    return 0
}

# =============================================================================
# メイン処理
# =============================================================================
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Ultra AutoTrade ヘルスチェックスクリプト

Options:
    --endpoint-only     /health エンドポイントのみチェック
    --env-only          環境変数のみチェック
    --connectivity      接続テスト（エンドポイント + Aave）
    --full              フルチェック（デフォルト）
    --verbose, -v       詳細出力
    --help, -h          このヘルプを表示

Environment Variables:
    HEALTH_URL          /health エンドポイント URL (default: http://localhost:8000/health)
    STATUS_URL          MonitoringService ステータス URL
    AAVE_STATUS_URL     Aave ステータス URL
    TIMEOUT             HTTP タイムアウト秒数 (default: 10)
    VERBOSE             詳細出力 (true/false)

Exit Codes:
    0   全てのチェックが成功
    1   いずれかのチェックが失敗
EOF
}

main() {
    local mode="full"

    # 引数解析
    while [[ $# -gt 0 ]]; do
        case $1 in
            --endpoint-only)
                mode="endpoint"
                shift
                ;;
            --env-only)
                mode="env"
                shift
                ;;
            --connectivity)
                mode="connectivity"
                shift
                ;;
            --full)
                mode="full"
                shift
                ;;
            --verbose|-v)
                VERBOSE="true"
                shift
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    echo "=========================================="
    echo "Ultra AutoTrade Health Check"
    echo "Mode: ${mode}"
    echo "=========================================="
    echo ""

    local failed=0

    case ${mode} in
        endpoint)
            check_health_endpoint || ((failed++))
            ;;
        env)
            check_environment_variables || ((failed++))
            ;;
        connectivity)
            check_health_endpoint || ((failed++))
            check_monitoring_status || ((failed++))
            check_aave_connection || ((failed++))
            ;;
        full)
            check_health_endpoint || ((failed++))
            check_monitoring_status || ((failed++))
            check_aave_connection || ((failed++))
            check_state_file || ((failed++))
            ;;
    esac

    echo ""
    echo "=========================================="
    if [[ ${failed} -eq 0 ]]; then
        log_success "All checks passed"
        echo "=========================================="
        exit 0
    else
        log_error "${failed} check(s) failed"
        echo "=========================================="
        exit 1
    fi
}

main "$@"
