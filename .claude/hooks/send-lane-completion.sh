#!/usr/bin/env bash
# send-lane-completion.sh — Slack 構造化通知 (Block Kit + jq -n)
#
# 使い方:
#   # 短縮形式 (3 引数)
#   send-lane-completion.sh <lane> <phase> <status>
#
#   # 完全形式 (8 引数、既存互換)
#   send-lane-completion.sh <lane> <phase> <status> <root_cause> <duration_sec> <files_count> <tier> <next_action>
#
#   # Dry run (curl をスキップして payload を stdout へ)
#   DRY_RUN=1 send-lane-completion.sh <lane> <phase> <status>
#
#   # WEBHOOK override
#   SLACK_WEBHOOK_URL=https://... send-lane-completion.sh ...
#
# WEBHOOK 取得経路 (上から順に検索):
#   1. 環境変数 SLACK_WEBHOOK_URL
#   2. ローカル <git root>/.env.production の SLACK_WEBHOOK_URL=
#   3. SSH root@5.223.88.14 で Hetzner (ASSIST ONE) 上の .env.production
#
# 終了コード: 200 OK → 0, それ以外 → 1

set -euo pipefail

LANE="${1:-unknown}"
PHASE="${2:-unknown}"
STATUS="${3:-unknown}"
ROOT_CAUSE="${4:-}"
DURATION="${5:-}"
FILES_COUNT="${6:-}"
TIER="${7:-}"
NEXT_ACTION="${8:-}"

# Stop hook として無引数で呼ばれた場合 (lane/phase/status が全て unknown) は通知しない。
# settings.json の Stop イベント登録では positional 引数が渡らず "unknown" 連発で
# Slack が flood する (2026-05-21 night-mode で背景エージェント Stop 多発時に顕在化)。
# 明示的に lane 等を指定した正規呼び出し (Agent Teams lane 完了通知) のみ通知する。
if [[ "${LANE}" == "unknown" && "${PHASE}" == "unknown" && "${STATUS}" == "unknown" ]]; then
  exit 0
fi

# 数値フィールドを jq --argjson 用に整形 (空 → null, 数値 → そのまま, 非数値 → null)
to_jsonnum() {
  local v="$1"
  if [[ -z "$v" ]]; then
    echo "null"
  elif [[ "$v" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
    echo "$v"
  else
    echo "null"
  fi
}

DURATION_JSON=$(to_jsonnum "$DURATION")
FILES_JSON=$(to_jsonnum "$FILES_COUNT")

# WEBHOOK 取得
if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  WEBHOOK="$SLACK_WEBHOOK_URL"
elif [[ -f "${HOME}/.claude-uata/secrets/slack.env" ]]; then
  WEBHOOK=$(grep "^SLACK_WEBHOOK_URL=" "${HOME}/.claude-uata/secrets/slack.env" | head -1 | cut -d= -f2-)
elif GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) && [[ -f "${GIT_ROOT}/.env.production" ]]; then
  WEBHOOK=$(grep "^SLACK_WEBHOOK_URL=" "${GIT_ROOT}/.env.production" | head -1 | cut -d= -f2-)
elif [[ -f "${HOME}/.ssh/hetzner_assistone_production" ]]; then
  WEBHOOK=$(ssh -i ~/.ssh/hetzner_assistone_production root@5.223.88.14 \
    'grep SLACK_WEBHOOK_URL /opt/ultra-autotrade/.env.production | head -1 | cut -d= -f2-' 2>/dev/null || true)
fi

if [[ -z "${WEBHOOK:-}" ]]; then
  echo "[send-lane-completion] WARN: SLACK_WEBHOOK_URL 未取得 — Slack 通知をスキップ" >&2
  exit 0
fi

# status に応じた絵文字
case "$STATUS" in
  success)  EMOJI="✅" ;;
  blocked)  EMOJI="🚧" ;;
  partial)  EMOJI="⚠️" ;;
  failure)  EMOJI="❌" ;;
  *)        EMOJI="📊" ;;
esac

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Slack Block Kit payload を jq -n で組立 (全文字列引数を --arg で自動エスケープ)
PAYLOAD=$(jq -n \
  --arg   lane         "$LANE" \
  --arg   phase        "$PHASE" \
  --arg   status       "$STATUS" \
  --arg   emoji        "$EMOJI" \
  --arg   root_cause   "$ROOT_CAUSE" \
  --argjson duration   "$DURATION_JSON" \
  --argjson files      "$FILES_JSON" \
  --arg   tier         "$TIER" \
  --arg   next_action  "$NEXT_ACTION" \
  --arg   timestamp    "$TIMESTAMP" \
  '
    # 詳細フィールドのうち空のものを除外した辞書
    ({
      root_cause:      $root_cause,
      duration_sec:    $duration,
      files_to_modify: $files,
      tier:            $tier,
      next_action:     $next_action,
      timestamp:       $timestamp
    }
    | to_entries
    | map(select(.value != null and .value != ""))
    | from_entries) as $details
    |
    {
      text: ($emoji + " Lane " + $lane + " / phase=" + $phase + " / status=" + $status),
      blocks: ([
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: ($emoji + " *Lane:* `" + $lane + "`\n*Phase:* `" + $phase + "`\n*Status:* `" + $status + "`")
          }
        }
      ] + (if ($details | length) > 0 then [
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: ("```\n" + ($details | tojson) + "\n```")
          }
        }
      ] else [] end))
    }
  ')

if [[ "${DRY_RUN:-0}" = "1" ]]; then
  echo "$PAYLOAD"
  exit 0
fi

# 送信 & HTTP 応答確認
RESP=$(curl -sS -w "\nHTTP_CODE=%{http_code}" -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  --data "$PAYLOAD")
HTTP_CODE=$(printf '%s\n' "$RESP" | tail -n1 | cut -d= -f2)
BODY=$(printf '%s\n' "$RESP" | sed '$d')

echo "[send-lane-completion] HTTP=${HTTP_CODE} body=${BODY}"

if [[ "$HTTP_CODE" = "200" ]]; then
  exit 0
else
  echo "[send-lane-completion] ERROR: Slack 通知失敗 (HTTP=${HTTP_CODE})" >&2
  exit 1
fi
