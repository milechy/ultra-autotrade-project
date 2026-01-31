#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-}"
MAX_CHARS="${MAX_CHARS:-120000}"

# ===== Diff generation =====
if [[ -z "${BASE_REF}" ]]; then
  git add -N . >/dev/null 2>&1 || true
  DIFF_CMD=(git diff --no-color --unified=1)
else
  DIFF_CMD=(git diff --no-color --unified=1 "${BASE_REF}...HEAD")
fi

DIFF="$("${DIFF_CMD[@]}" \
  ':(exclude)*.lock' \
  ':(exclude)*package-lock.json' \
  ':(exclude)*pnpm-lock.yaml' \
  ':(exclude)*yarn.lock' \
  ':(exclude)*.min.js' \
  ':(exclude)*dist/**' \
  ':(exclude)*build/**' \
  ':(exclude)*.map' \
  ':(exclude)node_modules/**' \
  || true
)"

if [[ -z "${DIFF}" ]]; then
  echo "No diff."
  exit 0
fi

if (( ${#DIFF} > MAX_CHARS )); then
  echo "WARN: diff too large (${#DIFF} chars). Truncating to ${MAX_CHARS} chars." >&2
  DIFF="${DIFF:0:MAX_CHARS}"
fi

PROMPT="Review ONLY the provided git diff.
Be extremely concise and prioritize correctness and security.
Output ONLY the following sections with bullet points:
1) Critical (must-fix)
2) Risky
3) Nits
Format each bullet exactly:
[High|Med|Low] path:line - issue - fix
No preamble, no summary, no compliments."

printf "%s" "$DIFF" | codex review "$PROMPT"