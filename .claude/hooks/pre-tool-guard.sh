#!/bin/bash
# Lane 越境 + .env.production 並列書込 物理ブロック
# 環境変数 LANE_NAME / LANE_ROOT / LANE_PERMITS_ENV_WRITE を各 Lane で export

TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"
CWD=$(pwd)

# 1. .env.production への write ブロック (LANE_PERMITS_ENV_WRITE=1 の Lane のみ許可)
if echo "$TOOL_INPUT" | grep -qE "\.env\.production[^.]"; then
  if [ "${LANE_PERMITS_ENV_WRITE:-0}" != "1" ]; then
    case "$TOOL_NAME" in
      str_replace|create_file|Write|Edit|MultiEdit)
        echo "BLOCKED by hook: .env.production write not permitted in Lane ${LANE_NAME:-unknown}"
        exit 2
        ;;
    esac
  fi
fi

# 2. 他 Lane worktree への侵入ブロック
if [ -n "${LANE_ROOT:-}" ]; then
  for other in lane-c-gpt4o lane-d-knowledge lane-f-fee-verify lane-login-investigate lane-amt-investigate; do
    if [ "$other" != "$LANE_ROOT" ] && echo "$TOOL_INPUT" | grep -q "$other"; then
      case "$TOOL_NAME" in
        str_replace|create_file|Write|Edit|MultiEdit|Bash)
          if echo "$TOOL_INPUT" | grep -qE "(rm |mv |cp |> |>>)"; then
            echo "BLOCKED by hook: Lane ${LANE_NAME} cannot write to $other"
            exit 2
          fi
          ;;
      esac
    fi
  done
fi

# 3. main / Tier S ファイル編集ブロック (本日 5/14 全 Lane で禁止)
TIER_S_FILES="backend/app/main.py|requirements.txt|package.json|docker-compose|scheduled_tasks.py|monitoring_service.py|database.py|migrations/versions"
if echo "$TOOL_INPUT" | grep -qE "$TIER_S_FILES"; then
  case "$TOOL_NAME" in
    str_replace|create_file|Write|Edit|MultiEdit)
      echo "BLOCKED by hook: Tier S file edit not permitted today (Lane ${LANE_NAME})"
      exit 2
      ;;
  esac
fi

# 4. /api/ai/trigger 手動実行ブロック
if echo "$TOOL_INPUT" | grep -qE "(/api/ai/trigger|ai_trigger)"; then
  echo "BLOCKED by hook: /api/ai/trigger manual trigger禁止 (Lane ${LANE_NAME})"
  exit 2
fi

exit 0
