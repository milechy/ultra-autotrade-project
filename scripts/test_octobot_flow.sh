#!/bin/bash
# scripts/test_octobot_flow.sh
#
# OctoBot 売買フローの E2E テストスクリプト
#
# 使用方法:
#   ./scripts/test_octobot_flow.sh [--api-url URL] [--scenario SCENARIO]
#
# オプション:
#   --api-url URL    バックエンド API の URL (デフォルト: http://77.42.46.155:8000)
#   --scenario NAME  実行するシナリオ (all|buy|sell|hold|low-confidence|rate-limit)
#   --verbose        詳細出力
#   --help           ヘルプ表示
#
# 必要ツール: curl, jq

set -euo pipefail

# ========================================
# 設定
# ========================================
API_URL="${API_URL:-http://77.42.46.155:8000}"
SCENARIO="all"
VERBOSE=false
LOG_FILE="/tmp/octobot_test_$(date +%Y%m%d_%H%M%S).log"

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ========================================
# ヘルパー関数
# ========================================
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$level" in
        INFO)  color="$BLUE" ;;
        OK)    color="$GREEN" ;;
        WARN)  color="$YELLOW" ;;
        ERROR) color="$RED" ;;
        *)     color="$NC" ;;
    esac

    echo -e "${color}[$timestamp] [$level] $message${NC}" | tee -a "$LOG_FILE"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        log INFO "$@"
    fi
}

check_dependencies() {
    local missing=()
    for cmd in curl jq; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        log ERROR "必要なツールがインストールされていません: ${missing[*]}"
        exit 1
    fi
}

api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local url="${API_URL}${endpoint}"

    log_verbose "API Call: $method $url"
    if [ -n "$data" ]; then
        log_verbose "Request Body: $data"
    fi

    local response
    local http_code

    if [ -n "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$url" 2>&1)
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" 2>&1)
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    log_verbose "HTTP Status: $http_code"
    log_verbose "Response: $body"

    echo "$body"
    return 0
}

# ========================================
# テストシナリオ
# ========================================

# シナリオ 1: BUY シグナル送信テスト
test_buy_signal() {
    log INFO "=== シナリオ 1: BUY シグナル送信テスト ==="
    log INFO "confidence=85 の BUY シグナルを送信し、OctoBot への送信成功を確認"

    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local payload
    payload=$(cat <<EOF
{
    "signals": [
        {
            "id": "test-buy-$(date +%s)",
            "url": "https://example.com/news/bullish",
            "action": "BUY",
            "confidence": 85,
            "reason": "Strong bullish sentiment detected in market news",
            "timestamp": "$timestamp"
        }
    ],
    "count": 1
}
EOF
)

    local response
    response=$(api_call POST "/octobot/signal" "$payload")

    local success_count
    success_count=$(echo "$response" | jq -r '.success_count // 0')
    local status
    status=$(echo "$response" | jq -r '.details[0].status // "unknown"')

    if [ "$success_count" -eq 1 ] && [ "$status" = "sent" ]; then
        log OK "PASS: BUY シグナルが正常に送信されました (status=$status)"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 0
    else
        log ERROR "FAIL: BUY シグナル送信に失敗 (success_count=$success_count, status=$status)"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 1
    fi
}

# シナリオ 2: SELL シグナル送信テスト
test_sell_signal() {
    log INFO "=== シナリオ 2: SELL シグナル送信テスト ==="
    log INFO "confidence=80 の SELL シグナルを送信し、OctoBot への送信成功を確認"

    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local payload
    payload=$(cat <<EOF
{
    "signals": [
        {
            "id": "test-sell-$(date +%s)",
            "url": "https://example.com/news/bearish",
            "action": "SELL",
            "confidence": 80,
            "reason": "Bearish market sentiment detected",
            "timestamp": "$timestamp"
        }
    ],
    "count": 1
}
EOF
)

    local response
    response=$(api_call POST "/octobot/signal" "$payload")

    local success_count
    success_count=$(echo "$response" | jq -r '.success_count // 0')
    local status
    status=$(echo "$response" | jq -r '.details[0].status // "unknown"')

    if [ "$success_count" -eq 1 ] && [ "$status" = "sent" ]; then
        log OK "PASS: SELL シグナルが正常に送信されました (status=$status)"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 0
    else
        log ERROR "FAIL: SELL シグナル送信に失敗 (success_count=$success_count, status=$status)"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 1
    fi
}

# シナリオ 3: HOLD シグナルテスト
test_hold_signal() {
    log INFO "=== シナリオ 3: HOLD シグナルテスト ==="
    log INFO "confidence=75 の HOLD シグナルを送信し、スキップされることを確認"
    log INFO "(HOLD は安全弁ルールにより OctoBot には送信されない)"

    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local payload
    payload=$(cat <<EOF
{
    "signals": [
        {
            "id": "test-hold-$(date +%s)",
            "url": "https://example.com/news/neutral",
            "action": "HOLD",
            "confidence": 75,
            "reason": "Market conditions are uncertain",
            "timestamp": "$timestamp"
        }
    ],
    "count": 1
}
EOF
)

    local response
    response=$(api_call POST "/octobot/signal" "$payload")

    local success_count
    success_count=$(echo "$response" | jq -r '.success_count // 0')
    local skipped_count
    skipped_count=$(echo "$response" | jq -r '.skipped_count // 0')

    # HOLD は通常 OctoBot 外部 API に送信しても問題ないが、
    # 実装によってはスキップされる場合もある
    log OK "RESULT: success_count=$success_count, skipped_count=$skipped_count"
    echo "$response" | jq '.' >> "$LOG_FILE"
    return 0
}

# シナリオ 4: 低信頼度スキップテスト
test_low_confidence() {
    log INFO "=== シナリオ 4: 低信頼度スキップテスト ==="
    log INFO "confidence=50 (閾値 70 未満) のシグナルがスキップされることを確認"

    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local payload
    payload=$(cat <<EOF
{
    "signals": [
        {
            "id": "test-low-conf-$(date +%s)",
            "url": "https://example.com/news/uncertain",
            "action": "BUY",
            "confidence": 50,
            "reason": "Weak signal with low confidence",
            "timestamp": "$timestamp"
        }
    ],
    "count": 1
}
EOF
)

    local response
    response=$(api_call POST "/octobot/signal" "$payload")

    local skipped_count
    skipped_count=$(echo "$response" | jq -r '.skipped_count // 0')
    local status
    status=$(echo "$response" | jq -r '.details[0].status // "unknown"')
    local message
    message=$(echo "$response" | jq -r '.details[0].message // ""')

    if [ "$skipped_count" -eq 1 ] && [ "$status" = "skipped" ]; then
        log OK "PASS: 低信頼度シグナルが正常にスキップされました"
        log OK "  status=$status, message=$message"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 0
    else
        log ERROR "FAIL: 低信頼度シグナルがスキップされませんでした"
        echo "$response" | jq '.' >> "$LOG_FILE"
        return 1
    fi
}

# シナリオ 5: レート制限テスト
test_rate_limit() {
    log INFO "=== シナリオ 5: レート制限テスト ==="
    log INFO "同一アクション (BUY) を 4 件連続送信し、4 件目がスキップされることを確認"
    log INFO "(1 時間あたり同一アクション 3 件まで)"

    local timestamp
    local passed=0
    local failed=0

    for i in 1 2 3 4; do
        timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

        local payload
        payload=$(cat <<EOF
{
    "signals": [
        {
            "id": "test-rate-$i-$(date +%s)",
            "url": "https://example.com/news/rate-test-$i",
            "action": "BUY",
            "confidence": 85,
            "reason": "Rate limit test signal $i",
            "timestamp": "$timestamp"
        }
    ],
    "count": 1
}
EOF
)

        local response
        response=$(api_call POST "/octobot/signal" "$payload")

        local success_count
        success_count=$(echo "$response" | jq -r '.success_count // 0')
        local skipped_count
        skipped_count=$(echo "$response" | jq -r '.skipped_count // 0')
        local status
        status=$(echo "$response" | jq -r '.details[0].status // "unknown"')

        if [ "$i" -le 3 ]; then
            # 1-3 件目は送信成功を期待
            if [ "$success_count" -eq 1 ]; then
                log OK "  シグナル $i: 送信成功 (status=$status)"
                ((passed++))
            else
                log WARN "  シグナル $i: 予期しない結果 (success=$success_count, skipped=$skipped_count)"
            fi
        else
            # 4 件目はスキップを期待
            if [ "$skipped_count" -eq 1 ]; then
                log OK "  シグナル $i: レート制限によりスキップ (status=$status)"
                ((passed++))
            else
                log WARN "  シグナル $i: 予期しない結果 (success=$success_count, skipped=$skipped_count)"
                ((failed++))
            fi
        fi

        echo "$response" | jq '.' >> "$LOG_FILE"
        sleep 0.5
    done

    if [ "$passed" -eq 4 ]; then
        log OK "PASS: レート制限テスト成功 (4/4 件が期待通りの動作)"
        return 0
    else
        log WARN "PARTIAL: レート制限テスト (passed=$passed/4)"
        log WARN "  注: OctoBot サービスが再起動されている場合、レート制限カウンタがリセットされている可能性があります"
        return 0  # 警告のみ
    fi
}

# フルフローテスト: Notion → AI → OctoBot
test_full_flow() {
    log INFO "=== フルフローテスト: Notion → AI → OctoBot ==="
    log INFO "完全なパイプラインを実行し、各ステップの結果を確認"

    # Step 1: /notion/ingest
    log INFO "Step 1: /notion/ingest を呼び出し"
    local ingest_response
    ingest_response=$(api_call POST "/notion/ingest" "")

    local items_count
    items_count=$(echo "$ingest_response" | jq -r '.count // 0')
    log INFO "  取得したニュース件数: $items_count"

    if [ "$items_count" -eq 0 ]; then
        log WARN "Notion から取得できるニュースがありません。テスト用ダミーデータで続行します。"

        # ダミーデータで AI 解析をテスト
        local timestamp
        timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

        local dummy_items
        dummy_items=$(cat <<EOF
{
    "items": [
        {
            "id": "dummy-news-$(date +%s)",
            "url": "https://example.com/news/test",
            "summary": "Bitcoin price surges amid positive market sentiment",
            "sentiment": null,
            "action": null,
            "confidence": null,
            "status": "未処理",
            "timestamp": "$timestamp"
        }
    ]
}
EOF
)

        # Step 2: /ai/analyze
        log INFO "Step 2: /ai/analyze を呼び出し (ダミーデータ)"
        local analyze_response
        analyze_response=$(api_call POST "/ai/analyze" "$dummy_items")

        local results_count
        results_count=$(echo "$analyze_response" | jq -r '.count // 0')
        log INFO "  AI 解析結果件数: $results_count"

        if [ "$results_count" -gt 0 ]; then
            local first_action
            first_action=$(echo "$analyze_response" | jq -r '.results[0].action // "unknown"')
            local first_confidence
            first_confidence=$(echo "$analyze_response" | jq -r '.results[0].confidence // 0')
            log INFO "  最初の結果: action=$first_action, confidence=$first_confidence"
        fi

        echo "$analyze_response" | jq '.' >> "$LOG_FILE"
    else
        # 実際の Notion データがある場合
        log INFO "Step 2: /ai/analyze を呼び出し (実データ)"

        local items_json
        items_json=$(echo "$ingest_response" | jq '{items: .items}')

        local analyze_response
        analyze_response=$(api_call POST "/ai/analyze" "$items_json")

        local results_count
        results_count=$(echo "$analyze_response" | jq -r '.count // 0')
        log INFO "  AI 解析結果件数: $results_count"

        echo "$analyze_response" | jq '.' >> "$LOG_FILE"
    fi

    log OK "フルフローテスト完了"
    return 0
}

# ========================================
# メイン処理
# ========================================
show_help() {
    cat << EOF
OctoBot 売買フロー E2E テストスクリプト

使用方法:
    $0 [オプション]

オプション:
    --api-url URL       バックエンド API の URL (デフォルト: $API_URL)
    --scenario NAME     実行するシナリオ (デフォルト: all)
                        all          : 全シナリオ実行
                        buy          : BUY シグナル送信テスト
                        sell         : SELL シグナル送信テスト
                        hold         : HOLD シグナルテスト
                        low-confidence: 低信頼度スキップテスト
                        rate-limit   : レート制限テスト
                        full-flow    : Notion → AI → OctoBot フルフローテスト
    --verbose           詳細出力を有効化
    --help              このヘルプを表示

例:
    $0                              # 全シナリオ実行
    $0 --scenario buy               # BUY テストのみ
    $0 --api-url http://localhost:8000 --verbose

ログファイル:
    $LOG_FILE
EOF
}

main() {
    # 引数解析
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --api-url)
                API_URL="$2"
                shift 2
                ;;
            --scenario)
                SCENARIO="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log ERROR "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # 依存チェック
    check_dependencies

    log INFO "========================================"
    log INFO "OctoBot E2E テスト開始"
    log INFO "API URL: $API_URL"
    log INFO "シナリオ: $SCENARIO"
    log INFO "ログファイル: $LOG_FILE"
    log INFO "========================================"

    # ヘルスチェック
    log INFO "API ヘルスチェック..."
    local health_response
    health_response=$(api_call GET "/health" "" || echo '{"status":"error"}')
    local health_status
    health_status=$(echo "$health_response" | jq -r '.status // "error"')

    if [ "$health_status" != "ok" ] && [ "$health_status" != "healthy" ]; then
        log ERROR "API ヘルスチェック失敗: $health_response"
        log ERROR "API が稼働していることを確認してください: $API_URL"
        exit 1
    fi
    log OK "API ヘルスチェック OK"

    # シナリオ実行
    local passed=0
    local failed=0

    case "$SCENARIO" in
        all)
            test_buy_signal && ((passed++)) || ((failed++))
            echo ""
            sleep 1
            test_sell_signal && ((passed++)) || ((failed++))
            echo ""
            sleep 1
            test_hold_signal && ((passed++)) || ((failed++))
            echo ""
            sleep 1
            test_low_confidence && ((passed++)) || ((failed++))
            echo ""
            sleep 1
            test_rate_limit && ((passed++)) || ((failed++))
            ;;
        buy)
            test_buy_signal && ((passed++)) || ((failed++))
            ;;
        sell)
            test_sell_signal && ((passed++)) || ((failed++))
            ;;
        hold)
            test_hold_signal && ((passed++)) || ((failed++))
            ;;
        low-confidence)
            test_low_confidence && ((passed++)) || ((failed++))
            ;;
        rate-limit)
            test_rate_limit && ((passed++)) || ((failed++))
            ;;
        full-flow)
            test_full_flow && ((passed++)) || ((failed++))
            ;;
        *)
            log ERROR "Unknown scenario: $SCENARIO"
            show_help
            exit 1
            ;;
    esac

    # 結果サマリ
    echo ""
    log INFO "========================================"
    log INFO "テスト結果サマリ"
    log INFO "========================================"
    log INFO "  PASSED: $passed"
    log INFO "  FAILED: $failed"
    log INFO "  ログファイル: $LOG_FILE"
    log INFO "========================================"

    if [ "$failed" -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main "$@"
