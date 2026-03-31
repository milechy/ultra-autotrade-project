#!/bin/bash
# PostToolUse hook: git commit 前にdiff表示
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

if [ "$TOOL_NAME" = "bash" ]; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
  if echo "$COMMAND" | grep -q "git commit"; then
    echo "📋 コミット前のdiff確認:" >&2
    git diff --cached --stat >&2
    echo "---" >&2
    echo "⚠️  .env や secrets が含まれていないか確認してください" >&2
  fi
fi
exit 0
