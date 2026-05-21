#!/bin/bash
# load-claude-lessons.sh — SessionStart Hook for auto-Read of CLAUDE.lessons.md
# 2026-05-21 refactor で追加: CLAUDE.md 分割後 (core / lessons / ops) の lessons 強制 Read
#
# 設定: .claude/settings.json の hooks.SessionStart に登録
# 動作: Claude Code セッション開始時に CLAUDE.lessons.md 全文を additionalContext として注入
# 目的: lessons.md は auto-inject されないため、Hook で強制的に読ませる

set -uo pipefail

# repo root を解決 (dev VPS: /opt/ultra-autotrade/main / 本番 VPS: /opt/ultra-autotrade)
if [ -f "/opt/ultra-autotrade/main/CLAUDE.lessons.md" ]; then
  LESSONS_FILE="/opt/ultra-autotrade/main/CLAUDE.lessons.md"
elif [ -f "/opt/ultra-autotrade/CLAUDE.lessons.md" ]; then
  LESSONS_FILE="/opt/ultra-autotrade/CLAUDE.lessons.md"
elif [ -f "${CLAUDE_PROJECT_DIR:-.}/CLAUDE.lessons.md" ]; then
  LESSONS_FILE="${CLAUDE_PROJECT_DIR:-.}/CLAUDE.lessons.md"
else
  # fallback: 現在ディレクトリから 3 階層遡って探索
  LESSONS_FILE=""
  for d in . .. ../.. ../../..; do
    if [ -f "$d/CLAUDE.lessons.md" ]; then
      LESSONS_FILE="$d/CLAUDE.lessons.md"
      break
    fi
  done
fi

if [ -z "$LESSONS_FILE" ] || [ ! -f "$LESSONS_FILE" ]; then
  # lessons file が見つからない場合は no-op (CI 環境等で誤動作させない)
  cat <<EOF
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"[load-claude-lessons.sh] CLAUDE.lessons.md が見つかりません。朝プロトコル §9 Step 0 を手動で実行してください。"}}
EOF
  exit 0
fi

LESSONS_CONTENT=$(cat "$LESSONS_FILE")

# JSON エスケープ (jq があれば jq、なければ python3)
if command -v jq >/dev/null 2>&1; then
  ESCAPED=$(jq -Rs . <<<"$LESSONS_CONTENT")
elif command -v python3 >/dev/null 2>&1; then
  ESCAPED=$(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$LESSONS_CONTENT")
else
  # 最低限のエスケープ (jq / python3 がない環境向け fallback)
  ESCAPED="\"$(echo "$LESSONS_CONTENT" | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/' | tr -d '\n')\""
fi

cat <<EOF
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":${ESCAPED}}}
EOF
