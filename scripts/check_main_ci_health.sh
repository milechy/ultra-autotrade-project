#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/check_main_ci_health.sh
#
# Ultra AutoTrade mainブランチのCI健全性をチェックする参考実装。
# 実運用は ~/ft-automation/scripts/main_ci_health_check.sh + launchd で行う。
#
# 使い方:
#   bash scripts/check_main_ci_health.sh           # 直近24h チェック
#   bash scripts/check_main_ci_health.sh --hours 48  # 直近48h チェック
#   bash scripts/check_main_ci_health.sh --dry-run   # Slack通知しない
#
# 依存: gh CLI、jq、curl
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="milechy/ultra-autotrade-project"
HOURS=24
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --hours) shift; HOURS="${1:-24}" ;;
    --dry-run) DRY_RUN=true ;;
  esac
done

SINCE=$(date -u -v -"${HOURS}H" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
        date -u -d "${HOURS} hours ago" +"%Y-%m-%dT%H:%M:%SZ")

echo "[check_main_ci_health] Checking since $SINCE ..."

FAILED_JSON=$(gh api \
  "repos/${REPO}/actions/runs?branch=main&per_page=50" \
  --jq "[.workflow_runs[] |
    select(.conclusion == \"failure\" and .created_at > \"${SINCE}\") |
    {name: .name, url: .html_url, sha: .head_sha[0:7], at: .created_at}
  ]")

COUNT=$(echo "$FAILED_JSON" | jq 'length')

echo "[check_main_ci_health] Failed runs: ${COUNT}"

if [[ "$COUNT" -gt 0 ]]; then
  echo "$FAILED_JSON" | jq -r '.[] | "  ❌ \(.name) (\(.sha)) \(.url)"'
fi

if [[ "$COUNT" -gt 0 ]] && [[ "$DRY_RUN" == "false" ]]; then
  WEBHOOK="${SLACK_WEBHOOK_URL:-}"
  if [[ -n "$WEBHOOK" ]]; then
    SUMMARY=$(echo "$FAILED_JSON" | jq -r '.[] | "• \(.name) (\(.sha)) \(.url)"' | head -10)
    curl -s -X POST "$WEBHOOK" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg text "🚨 main ブランチCI失敗 ${COUNT}件 (直近${HOURS}h)\n${SUMMARY}" '{text: $text}')"
    echo "[check_main_ci_health] Slack notified."
  else
    echo "[check_main_ci_health] WARN: SLACK_WEBHOOK_URL not set, skipping Slack notification"
  fi
fi
