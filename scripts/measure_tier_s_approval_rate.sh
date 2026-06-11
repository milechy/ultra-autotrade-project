#!/usr/bin/env bash
# scripts/measure_tier_s_approval_rate.sh
#
# Ultra AutoTrade ローンチ条件 3「本番 Tier S 操作の人間承認率 100%」計測スクリプト
# (docs/launch_decision_criteria_v2.md §3)
#
# 計測対象 (3 軸):
#   (a) Tier S ファイルを触った merged PR の Approve 率 (reviews に APPROVED >= 1)
#   (b) main への直 push 数 (squash merge 誤検出対策の 2 段判定:
#       git log --first-parent --no-merges 候補 → gh api commits/<sha>/pulls で
#       PR 紐付きゼロのものだけを「真の直 push」と判定)
#   (c) --no-verify / --dangerously-skip-permissions の実行数
#       (本ホストの ~/.bash_history + Claude Code projects 配下 *.jsonl の
#        "command":"..." フィールドのみ = 言及ではなく実行を集計)
#
# ⚠ READ-ONLY 宣言:
#   本スクリプトは GitHub への read API (gh pr list / gh api GET) と
#   ローカル read (git log / grep) のみを行う。リポジトリ・DB・本番環境への
#   書き込みは一切しない。唯一の外部送信は --slack 指定時の Slack webhook POST。
#
# Usage:
#   ./scripts/measure_tier_s_approval_rate.sh                # 直近 14 日
#   ./scripts/measure_tier_s_approval_rate.sh --days 30      # 直近 30 日
#   ./scripts/measure_tier_s_approval_rate.sh --limit 500    # PR 取得上限変更
#   ./scripts/measure_tier_s_approval_rate.sh --json         # 機械可読 JSON 出力
#   ./scripts/measure_tier_s_approval_rate.sh --slack        # Slack 通知あり
#   ./scripts/measure_tier_s_approval_rate.sh --dry-run      # 実行コマンド表示のみ
#
# 依存: gh (認証済み) / jq / git / awk
#
# Exit codes:
#   0 -- 条件 3 総合 PASS (approve_rate==100% && 直push==0 && no-verify(計測可能分)==0)
#   1 -- 条件 3 総合 FAIL もしくは不正引数
#
# 出力形式 (launch_gate.sh 準拠):
#   [PASS] L3a tier_s_approve: <summary>
#   [FAIL] L3b direct_push:    <summary>
#   [SKIP] <reason>

set -euo pipefail

# =============================================================================
# 設定 / 引数
# =============================================================================
REPO="milechy/ultra-autotrade-project"
DAYS=14
LIMIT=300
JSON=false
SLACK=false
DRY_RUN=false
ENV_FILE="${ENV_FILE:-/opt/ultra-autotrade/.env.production}"

usage() {
  grep -E '^# ' "$0" | head -40 | cut -c3-
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)
      DAYS="${2:?--days requires a value}"
      shift 2
      ;;
    --days=*) DAYS="${1#--days=}"; shift ;;
    --limit)
      LIMIT="${2:?--limit requires a value}"
      shift 2
      ;;
    --limit=*) LIMIT="${1#--limit=}"; shift ;;
    --json) JSON=true; shift ;;
    --slack) SLACK=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "[FAIL] 不正引数: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
  echo "[FAIL] --days / --limit は正の整数で指定してください" >&2
  exit 1
fi

for dep in gh jq git awk; do
  if ! command -v "$dep" > /dev/null 2>&1; then
    echo "[FAIL] 依存コマンド不在: $dep" >&2
    exit 1
  fi
done

# date: Mac (BSD) / Linux (GNU) 両対応
SINCE="$(date -u -v "-${DAYS}d" +%F 2> /dev/null || date -u -d "${DAYS} days ago" +%F)"
GENERATED_AT="$(date -u +%FT%TZ)"

# Tier S ファイルパターン (実パス準拠 ERE。CLAUDE.md「Tier S」一覧と対応)
# NOTE: pyproject.toml は repo root に実在するため (backend/)? で両方を許容する
TIER_S_PATTERN='^(backend/app/main\.py|backend/requirements\.txt|(backend/)?pyproject\.toml|frontend/package(-lock)?\.json|\.github/workflows/ci\.yml|docker-compose\.(production|staging)\.yml|docker/nginx/upstream\.(production|staging)\.conf|backend/alembic/versions/.*\.py|backend/app/database\.py|backend/app/automation/(scheduled_tasks|monitoring_service|workflow)\.py|CLAUDE(\.lessons)?\.md)$'

# =============================================================================
# --dry-run: 実行予定コマンドの表示のみ (ネットワークアクセスなし)
# =============================================================================
if [[ "$DRY_RUN" == "true" ]]; then
  cat << EOF
[DRY-RUN] read-only 計測で実行する予定のコマンド (DAYS=${DAYS} / SINCE=${SINCE} / LIMIT=${LIMIT}):
  (a) gh pr list --repo ${REPO} --state merged --search "merged:>=${SINCE}" \\
        --limit ${LIMIT} --json number,title,reviews,files,mergedAt
  (b) git log origin/main --first-parent --no-merges --since="${DAYS} days ago" --pretty='%H|%an|%s'
      + 候補ごとに gh api repos/${REPO}/commits/<sha>/pulls --jq length
  (c) grep -E -- '--no-verify|--dangerously-skip-permissions' ~/.bash_history
      + \${CLAUDE_PROJECTS_DIR:-\$HOME/.claude*/projects} 配下 *.jsonl の "command":" フィールド集計
  Slack 送信: $([[ "$SLACK" == "true" ]] && echo "あり (${ENV_FILE} の SLACK_WEBHOOK_URL)" || echo "なし")
EOF
  exit 0
fi

# =============================================================================
# (a) Tier S PR Approve 率
# =============================================================================
PRS_JSON="$(gh pr list --repo "$REPO" --state merged \
  --search "merged:>=${SINCE}" --limit "$LIMIT" \
  --json number,title,reviews,files,mergedAt)"

TIER_S_JSON="$(jq --arg re "$TIER_S_PATTERN" \
  '[ .[] | select(any(.files[]?.path; test($re))) ]' <<< "$PRS_JSON")"

TIER_S_TOTAL="$(jq 'length' <<< "$TIER_S_JSON")"
TIER_S_APPROVED="$(jq '[ .[] | select(any(.reviews[]?; .state == "APPROVED")) ] | length' <<< "$TIER_S_JSON")"

if [[ "$TIER_S_TOTAL" -gt 0 ]]; then
  APPROVE_RATE="$(awk -v a="$TIER_S_APPROVED" -v t="$TIER_S_TOTAL" 'BEGIN { printf "%.1f", a / t * 100 }')"
else
  APPROVE_RATE="0.0"
fi

# gh の files フィールドは PR あたり 100 件上限 → 100 件ちょうどの PR は
# 一覧が打ち切られている可能性があり、Tier S ファイル見逃しの恐れ
TRUNCATED_PRS="$(jq -r '[ .[] | select((.files | length) >= 100) | .number ] | map(tostring) | join(",")' <<< "$PRS_JSON")"

TIER_S_UNAPPROVED_LIST="$(jq -r '[ .[] | select(any(.reviews[]?; .state == "APPROVED") | not) | "    - #\(.number) \(.title) (merged: \(.mergedAt))" ] | join("\n")' <<< "$TIER_S_JSON")"

if [[ "$TIER_S_TOTAL" -eq 0 ]]; then
  A_STATUS="PASS"
  A_SUMMARY="期間内 Tier S PR 0 件 (vacuous pass) / 対象 merged PR ${LIMIT}件上限内"
elif [[ "$TIER_S_APPROVED" -eq "$TIER_S_TOTAL" ]]; then
  A_STATUS="PASS"
  A_SUMMARY="Tier S PR ${TIER_S_TOTAL}件 / approved ${TIER_S_APPROVED}件 / approve_rate ${APPROVE_RATE}%"
else
  A_STATUS="FAIL"
  A_SUMMARY="Tier S PR ${TIER_S_TOTAL}件 / approved ${TIER_S_APPROVED}件 / approve_rate ${APPROVE_RATE}% (< 100%)"
fi

# =============================================================================
# (b) main 直 push 数 (squash merge 誤検出対策の 2 段判定)
# =============================================================================
# Stage 1: first-parent の非 merge コミット = 直 push 候補 (squash merge を含む)
declare -a DP_CANDIDATES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && DP_CANDIDATES+=("$line")
done < <(git log origin/main --first-parent --no-merges \
  --since="${DAYS} days ago" --pretty='%H|%an|%s' 2> /dev/null || true)

# Stage 2: PR 紐付き確認 (length==0 のみ真の直 push)
DIRECT_PUSH_COUNT=0
DP_UNKNOWN_COUNT=0
DP_LINES=""
DP_JSON_ITEMS="[]"
for cand in "${DP_CANDIDATES[@]+"${DP_CANDIDATES[@]}"}"; do
  sha="${cand%%|*}"
  rest="${cand#*|}"
  author="${rest%%|*}"
  subject="${rest#*|}"
  pr_count="$(gh api "repos/${REPO}/commits/${sha}/pulls" --jq 'length' 2> /dev/null || echo "ERR")"
  if [[ "$pr_count" == "ERR" ]]; then
    DP_UNKNOWN_COUNT=$((DP_UNKNOWN_COUNT + 1))
    DP_LINES+=$'\n'"    - ${sha:0:8} ${author}: ${subject} [WARN: PR 紐付き API 失敗 / 判定不能]"
  elif [[ "$pr_count" -eq 0 ]]; then
    DIRECT_PUSH_COUNT=$((DIRECT_PUSH_COUNT + 1))
    DP_LINES+=$'\n'"    - ${sha:0:8} ${author}: ${subject}"
    DP_JSON_ITEMS="$(jq --arg sha "$sha" --arg author "$author" --arg subject "$subject" \
      '. + [{sha: $sha, author: $author, subject: $subject}]' <<< "$DP_JSON_ITEMS")"
  fi
done

if [[ "$DIRECT_PUSH_COUNT" -gt 0 ]]; then
  B_STATUS="FAIL"
  B_SUMMARY="main 直 push ${DIRECT_PUSH_COUNT} 件 (候補 ${#DP_CANDIDATES[@]} 件中)"
elif [[ "$DP_UNKNOWN_COUNT" -gt 0 ]]; then
  B_STATUS="FAIL"
  B_SUMMARY="[FAIL] main 直 push 判定不能 ${DP_UNKNOWN_COUNT} 件 (gh api 失敗 / PR 紐付き確認不可 — fail-closed)"
else
  B_STATUS="PASS"
  B_SUMMARY="main 直 push 0 件 (候補 ${#DP_CANDIDATES[@]} 件は全て PR 紐付き)"
fi

# =============================================================================
# (c) --no-verify / --dangerously-skip-permissions 実行数 (本ホストのみ)
# =============================================================================
NV_PATTERN='--no-verify|--dangerously-skip-permissions'

# c-1: ~/.bash_history (history の行 = 実行コマンド)
#   言及 (grep 自身 / ペーストされた markdown 表 `|...` / コメント `#` / 番号付きリスト) は除外
HIST_COUNT=0
HIST_NV_COUNT=0
HIST_DSP_COUNT=0
HISTORY_FILE="${HOME}/.bash_history"
_hist_exec_lines() {
  grep -E -- "$NV_PATTERN" "$HISTORY_FILE" 2> /dev/null |
    grep -v 'grep' |
    grep -vE '^[[:space:]]*([|#]|[0-9]+\.[[:space:]])' || true
}
if [[ -f "$HISTORY_FILE" ]]; then
  HIST_NV_COUNT="$(_hist_exec_lines | grep -c -- '--no-verify' || true)"
  HIST_DSP_COUNT="$(_hist_exec_lines | grep -c -- '--dangerously-skip-permissions' || true)"
  HIST_COUNT="$(_hist_exec_lines | wc -l | tr -d '[:space:]')"
fi

# c-2: Claude Code projects 配下 *.jsonl の "command":"..." フィールドのみ
#      (= Bash ツールで実際に実行されたコマンド。本文中の言及と区別する)
JSONL_COUNT=0
declare -a PROJ_DIRS=()
if [[ -n "${CLAUDE_PROJECTS_DIR:-}" ]]; then
  [[ -d "$CLAUDE_PROJECTS_DIR" ]] && PROJ_DIRS+=("$CLAUDE_PROJECTS_DIR")
else
  for d in "$HOME"/.claude*/projects; do
    [[ -d "$d" ]] && PROJ_DIRS+=("$d")
  done
fi
for d in "${PROJ_DIRS[@]+"${PROJ_DIRS[@]}"}"; do
  # -oE で command フィールド先頭〜フラグまでを抽出し、計測用 grep/rg 自身は除外
  c="$({
    find "$d" -name '*.jsonl' -mtime "-${DAYS}" -print0 2> /dev/null |
      xargs -0 -r grep -ohE '"command":"[^"]*(--no-verify|--dangerously-skip-permissions)' 2> /dev/null || true
  } | grep -cvE '"command":"[[:space:]]*(grep|rg)[[:space:]]' || true)"
  JSONL_COUNT=$((JSONL_COUNT + ${c:-0}))
done

NV_TOTAL=$((HIST_COUNT + JSONL_COUNT))
if [[ "$NV_TOTAL" -eq 0 ]]; then
  C_STATUS="PASS"
  C_SUMMARY="本ホスト no-verify/skip-permissions 実行 0 件 (bash_history 0 + claude jsonl 0)"
else
  C_STATUS="FAIL"
  C_SUMMARY="本ホスト no-verify/skip-permissions 実行 ${NV_TOTAL} 件 (bash_history ${HIST_COUNT} [no-verify ${HIST_NV_COUNT} / skip-permissions ${HIST_DSP_COUNT}] + claude jsonl ${JSONL_COUNT})"
fi

# 計測不能分 (必ず出力)
SKIP_LINE_1='[SKIP] no-verify(他ホスト): UNMEASURABLE — 本番 VPS / Mac の shell history は本ホストから観測不能。TODO: 各ホストで本スクリプトを実行'
SKIP_LINE_2='[SKIP] Step 0 スキップ: 記録機能未実装 (criteria_v2 §3.4)'

# =============================================================================
# 総合判定
# =============================================================================
if [[ "$A_STATUS" == "PASS" && "$B_STATUS" == "PASS" && "$C_STATUS" == "PASS" ]]; then
  OVERALL="PASS"
  EXIT_CODE=0
else
  OVERALL="FAIL"
  EXIT_CODE=1
fi

# =============================================================================
# 出力
# =============================================================================
if [[ "$JSON" == "true" ]]; then
  jq -n \
    --arg script "measure_tier_s_approval_rate" \
    --arg generated_at "$GENERATED_AT" \
    --argjson days "$DAYS" \
    --arg since "$SINCE" \
    --arg repo "$REPO" \
    --argjson tier_s_total "$TIER_S_TOTAL" \
    --argjson tier_s_approved "$TIER_S_APPROVED" \
    --arg approve_rate "$APPROVE_RATE" \
    --arg a_status "$A_STATUS" \
    --arg truncated_prs "$TRUNCATED_PRS" \
    --argjson direct_push_count "$DIRECT_PUSH_COUNT" \
    --argjson direct_push_unknown "$DP_UNKNOWN_COUNT" \
    --argjson direct_push_commits "$DP_JSON_ITEMS" \
    --arg b_status "$B_STATUS" \
    --argjson hist_count "$HIST_COUNT" \
    --argjson hist_nv_count "$HIST_NV_COUNT" \
    --argjson hist_dsp_count "$HIST_DSP_COUNT" \
    --argjson jsonl_count "$JSONL_COUNT" \
    --arg c_status "$C_STATUS" \
    --arg skip1 "$SKIP_LINE_1" \
    --arg skip2 "$SKIP_LINE_2" \
    --arg overall "$OVERALL" \
    --argjson exit_code "$EXIT_CODE" \
    '{
      script: $script,
      generated_at: $generated_at,
      days: $days,
      since: $since,
      repo: $repo,
      tier_s_approve: {
        status: $a_status,
        total: $tier_s_total,
        approved: $tier_s_approved,
        approve_rate_pct: ($approve_rate | tonumber),
        files_truncated_pr_numbers: ($truncated_prs | if . == "" then [] else split(",") end)
      },
      direct_push: {
        status: $b_status,
        count: $direct_push_count,
        unknown: $direct_push_unknown,
        commits: $direct_push_commits
      },
      no_verify_local: {
        status: $c_status,
        bash_history: $hist_count,
        bash_history_no_verify: $hist_nv_count,
        bash_history_skip_permissions: $hist_dsp_count,
        claude_jsonl: $jsonl_count
      },
      skips: [$skip1, $skip2],
      overall: $overall,
      exit_code: $exit_code
    }'
else
  echo "=== ローンチ条件 3: Tier S 人間承認率 100% 計測 (read-only) ==="
  echo "repo: ${REPO} / 期間: 直近 ${DAYS} 日 (since ${SINCE}) / PR 取得上限: ${LIMIT}"
  echo ""
  echo "[${A_STATUS}] L3a tier_s_approve: ${A_SUMMARY}"
  if [[ "$A_STATUS" == "FAIL" && -n "$TIER_S_UNAPPROVED_LIST" ]]; then
    echo "  未 Approve の Tier S PR:"
    echo "$TIER_S_UNAPPROVED_LIST"
  fi
  if [[ -n "$TRUNCATED_PRS" ]]; then
    echo "  [WARN] files 100件上限到達 PR (Tier S 判定漏れの可能性): #${TRUNCATED_PRS//,/, #}"
  fi
  echo "[${B_STATUS}] L3b direct_push: ${B_SUMMARY}"
  if [[ -n "$DP_LINES" ]]; then
    echo "  直 push コミット一覧:${DP_LINES}"
  fi
  echo "[${C_STATUS}] L3c no_verify(本ホスト): ${C_SUMMARY}"
  echo "${SKIP_LINE_1}"
  echo "${SKIP_LINE_2}"
  echo ""
  echo "条件 3 総合: ${OVERALL} (exit ${EXIT_CODE})"
  if [[ "$OVERALL" == "FAIL" ]]; then
    echo "NOTE: 条件3達成には PR Approve 運用の開始が別途必要 (現状 Tier S PR に reviewer Approve が付与されていない)"
  fi
fi

# =============================================================================
# Slack 通知 (--slack 時のみ / 失敗してもスクリプトは fail しない)
# =============================================================================
if [[ "$SLACK" == "true" ]]; then
  SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
  if [[ -z "$SLACK_WEBHOOK_URL" && -f "$ENV_FILE" ]]; then
    SLACK_WEBHOOK_URL="$(grep '^SLACK_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
  fi
  if [[ -n "$SLACK_WEBHOOK_URL" ]]; then
    SLACK_TEXT="📐 ローンチ条件3 (Tier S 承認率) 計測: *${OVERALL}*\n[${A_STATUS}] approve_rate ${APPROVE_RATE}% (${TIER_S_APPROVED}/${TIER_S_TOTAL})\n[${B_STATUS}] main 直 push ${DIRECT_PUSH_COUNT} 件\n[${C_STATUS}] no-verify 本ホスト ${NV_TOTAL} 件\n(他ホスト no-verify / Step 0 記録は SKIP)"
    curl -s -X POST "$SLACK_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"${SLACK_TEXT}\"}" > /dev/null 2>&1 || true
  fi
fi

exit "$EXIT_CODE"
