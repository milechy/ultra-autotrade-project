#!/bin/bash
# UATa Pushover Notification Helper
# 配置先: scripts/uata-pushover-notify.sh
# 用途: 他スクリプトから source して関数として使用、または直接 ./uata-pushover-notify.sh test で動作確認
# Required env: PUSHOVER_APP_TOKEN, PUSHOVER_USER_KEY (~/.claude-uata/secrets/pushover.env)

set -uo pipefail

UATA_CONFIG="${UATA_CONFIG:-$HOME/.claude-uata}"
PUSHOVER_API="https://api.pushover.net/1/messages.json"

# 環境変数読み込み
[ -f "$UATA_CONFIG/secrets/pushover.env" ] && source "$UATA_CONFIG/secrets/pushover.env"

# ─── 静音時間帯判定 ───
# JST 22:00-05:59 を静音時間帯とする。
# テスト用: _UATA_TEST_HOUR=22 で時刻を上書き可能。
_uata_is_quiet_hours() {
    local jst_hour
    if [[ -n "${_UATA_TEST_HOUR:-}" ]]; then
        jst_hour="$_UATA_TEST_HOUR"
    else
        jst_hour="$(TZ=Asia/Tokyo date +%H)"
    fi
    # 22:00-23:59 または 00:00-05:59 → 静音時間帯
    if [[ "$jst_hour" -ge 22 ]] || [[ "$jst_hour" -lt 6 ]]; then
        return 0  # quiet
    fi
    return 1  # not quiet
}

# ─── 通知関数 ───

# Critical: priority=2 (深夜でも鳴動、了解確認まで再送)
# 時間帯問わず常に Critical — 深夜でも必須の緊急通知用
# 使い方: uata_notify_critical "Title" "Message body"
uata_notify_critical() {
    local title="${1:-UATa CRITICAL}"
    local message="${2:-Critical alert from UATa}"
    local url="${3:-}"

    if [ -z "${PUSHOVER_APP_TOKEN:-}" ] || [ -z "${PUSHOVER_USER_KEY:-}" ]; then
        echo "ERROR: Pushover credentials not set" >&2
        return 1
    fi

    local response
    response=$(curl -s --max-time 30 \
        --form-string "token=$PUSHOVER_APP_TOKEN" \
        --form-string "user=$PUSHOVER_USER_KEY" \
        --form-string "title=$title" \
        --form-string "message=$message" \
        --form-string "priority=2" \
        --form-string "retry=60" \
        --form-string "expire=3600" \
        --form-string "sound=siren" \
        ${url:+--form-string "url=$url"} \
        "$PUSHOVER_API" 2>&1)

    if echo "$response" | grep -q '"status":1'; then
        echo "[$(date +%H:%M:%S)] Pushover CRITICAL sent: $title"
        return 0
    else
        echo "[$(date +%H:%M:%S)] Pushover CRITICAL FAILED: $response" >&2
        return 1
    fi
}

# High: priority=1 (通常通知より目立つが鳴動なし)
# 22:00-05:59 JST は自動的に Low priority (-1) に格下げして hkobayashi を起こさない
uata_notify_high() {
    local title="${1:-UATa High}"
    local message="${2:-High priority alert}"
    local url="${3:-}"

    if [ -z "${PUSHOVER_APP_TOKEN:-}" ] || [ -z "${PUSHOVER_USER_KEY:-}" ]; then
        echo "ERROR: Pushover credentials not set" >&2
        return 1
    fi

    # 静音時間帯 (22:00-05:59 JST) は Low priority に格下げ
    local priority=1
    if _uata_is_quiet_hours; then
        priority=-1
        echo "[$(date +%H:%M:%S)] Quiet hours (JST): high→low downgrade: $title"
    fi

    local response
    response=$(curl -s --max-time 30 \
        --form-string "token=$PUSHOVER_APP_TOKEN" \
        --form-string "user=$PUSHOVER_USER_KEY" \
        --form-string "title=$title" \
        --form-string "message=$message" \
        --form-string "priority=$priority" \
        ${url:+--form-string "url=$url"} \
        "$PUSHOVER_API")

    if echo "$response" | grep -q '"status":1'; then
        echo "[$(date +%H:%M:%S)] Pushover HIGH(p=$priority) sent: $title"
        return 0
    else
        echo "[$(date +%H:%M:%S)] Pushover HIGH FAILED" >&2
        return 1
    fi
}

# Normal: priority=0 (通常)
uata_notify_normal() {
    local title="${1:-UATa}"
    local message="${2:-Notification}"
    local url="${3:-}"

    if [ -z "${PUSHOVER_APP_TOKEN:-}" ] || [ -z "${PUSHOVER_USER_KEY:-}" ]; then
        echo "ERROR: Pushover credentials not set" >&2
        return 1
    fi

    curl -s --max-time 30 \
        --form-string "token=$PUSHOVER_APP_TOKEN" \
        --form-string "user=$PUSHOVER_USER_KEY" \
        --form-string "title=$title" \
        --form-string "message=$message" \
        --form-string "priority=0" \
        ${url:+--form-string "url=$url"} \
        "$PUSHOVER_API" > /dev/null
}

# Low: priority=-1 (静かに、night-mode で hkobayashi を起こさない用)
uata_notify_low() {
    local title="${1:-UATa Info}"
    local message="${2:-Low priority info}"

    if [ -z "${PUSHOVER_APP_TOKEN:-}" ] || [ -z "${PUSHOVER_USER_KEY:-}" ]; then
        return 1
    fi

    curl -s --max-time 30 \
        --form-string "token=$PUSHOVER_APP_TOKEN" \
        --form-string "user=$PUSHOVER_USER_KEY" \
        --form-string "title=$title" \
        --form-string "message=$message" \
        --form-string "priority=-1" \
        "$PUSHOVER_API" > /dev/null
}

# ─── レート制限 (連投防止) ───
# 同じ通知を直近 N 分以内に送ったか確認、送ってたらスキップ
# 使い方: uata_notify_with_rate_limit "key" "function_name" "title" "message"
uata_notify_with_rate_limit() {
    local key="$1"
    local func="$2"
    local title="$3"
    local message="$4"
    local rate_window_min="${5:-60}"  # デフォルト60分

    local marker="$UATA_CONFIG/rate-limits/notify-$key.last"
    mkdir -p "$(dirname $marker)"

    if [ -f "$marker" ]; then
        local last_sent now age
        last_sent=$(cat "$marker")
        now=$(date +%s)
        age=$((now - last_sent))
        local threshold=$((rate_window_min * 60))
        if [ "$age" -lt "$threshold" ]; then
            echo "[$(date +%H:%M:%S)] Rate-limited: $key (last sent ${age}s ago, threshold ${threshold}s)"
            return 0
        fi
    fi

    $func "$title" "$message"
    date +%s > "$marker"
}

# ─── CLI 直接実行モード (テスト用) ───
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    case "${1:-help}" in
        test)
            echo "Sending test notifications..."
            uata_notify_normal "UATa Test" "Normal test from $(hostname) $(date +%H:%M:%S)"
            sleep 2
            uata_notify_high "UATa Test High" "High test from $(hostname) $(date +%H:%M:%S)"
            ;;
        critical)
            echo "Sending CRITICAL test..."
            uata_notify_critical "UATa Test CRITICAL" "Critical test from $(hostname) $(date +%H:%M:%S)"
            ;;
        normal)
            uata_notify_normal "${2:-UATa}" "${3:-Test message}"
            ;;
        high)
            uata_notify_high "${2:-UATa High}" "${3:-Test message}"
            ;;
        low)
            uata_notify_low "${2:-UATa Info}" "${3:-Test message}"
            ;;
        dry-run)
            # dry-run: 時刻をオーバーライドして quiet hours 判定のみ確認 (curl は送らない)
            # Usage: ./uata-pushover-notify.sh dry-run <hour>
            # Example: ./uata-pushover-notify.sh dry-run 22  → quiet
            #          ./uata-pushover-notify.sh dry-run 06  → normal
            test_hour="${2-}"
            if [[ -z "$test_hour" ]]; then
                echo "Usage: $0 dry-run <hour_0-23>"
                exit 1
            fi
            export _UATA_TEST_HOUR="$test_hour"
            if _uata_is_quiet_hours; then
                echo "[dry-run] hour=$test_hour JST → QUIET HOURS: high サブコマンドは low(-1) に格下げされます"
            else
                echo "[dry-run] hour=$test_hour JST → NORMAL HOURS: high サブコマンドは high(+1) で送信されます"
            fi
            echo "[dry-run] critical サブコマンドは時間帯問わず priority=2 で送信されます"
            ;;
        *)
            cat <<EOF
Usage: $0 <subcommand>

Subcommands:
  test      - Normal + High テスト送信
  critical  - Critical テスト送信 (鳴動、深夜でも起こす)
  normal "title" "message"
  high "title" "message"   ← 22:00-05:59 JST は自動的に low(-1) に格下げ
  low "title" "message"
  dry-run <hour>           - 時刻をオーバーライドして quiet hours 判定のみ確認 (curl なし)
                             例: dry-run 22 → quiet, dry-run 06 → normal

または source して使用:
  source ~/projects/ultra-autotrade/scripts/uata-pushover-notify.sh
  uata_notify_critical "Title" "Message"   # 時間帯問わず priority=2
  uata_notify_high "Title" "Message"       # 22:00-05:59 JST は自動 low 格下げ
EOF
            ;;
    esac
fi
