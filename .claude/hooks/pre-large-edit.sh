#!/bin/bash
# PreToolUse hook: 大規模変更の検知
# 50行以上の変更を含むeditに警告を出す

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

if [ "$TOOL_NAME" = "write" ] || [ "$TOOL_NAME" = "edit" ]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')
  LINE_COUNT=$(echo "$CONTENT" | wc -l)
  if [ "$LINE_COUNT" -gt 50 ]; then
    echo "⚠️  大規模変更検知: ${LINE_COUNT}行の変更。1関数ルールに違反していないか確認してください。" >&2
    exit 2
  fi
fi
exit 0
