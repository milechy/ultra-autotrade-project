#!/usr/bin/env bash
# scripts/auto_isolate.sh — 自走パイプラインのコンフリクト/バグ自動隔離
#
# 用途（docs/ops/agent_pipeline_v1.md §5 の実装）:
#   失敗を main / 作業ブランチに持ち込まず、worktree / 隔離ブランチに閉じ込める。
#   解決不能なものだけ人間にエスカレーションする。
#
# サブコマンド:
#   ./scripts/auto_isolate.sh rebase                 # origin/main に rebase。衝突→自動abort+隔離報告
#   ./scripts/auto_isolate.sh stash-guard            # 未コミット変更を stash に退避（delete vs modify衝突防止）
#   ./scripts/auto_isolate.sh quarantine <reason>    # 現在の変更を隔離ブランチに退避
#   ./scripts/auto_isolate.sh check-regression <cmd> # <cmd>(テスト) 実行。落ちたら隔離ブランチ作成
#
# 終了コード: 0=自動解決 / 1=人間エスカレーション必要 / 2=引数エラー
#
# 設計原則（CLAUDE.md 鉄則6「stash/未コミット変更を残さない」/ 鉄則3「rebase origin/main」）

set -uo pipefail   # -e は付けない（失敗を捕捉して判断するため）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT" || { echo "cd $PROJECT_ROOT 失敗" >&2; exit 2; }

ts() { date +%Y%m%d-%H%M%S 2>/dev/null || echo "nodate"; }
CUR_BRANCH="$(git branch --show-current 2>/dev/null || echo HEAD)"

cmd="${1:-}"

case "$cmd" in
  rebase)
    echo "=== auto_isolate: rebase origin/main ==="
    git fetch origin -q || { echo "fetch 失敗 → 人間判断"; exit 1; }
    if git rebase origin/main; then
      echo "✓ rebase 成功（衝突なし）"
      exit 0
    fi
    echo "⚠ rebase 衝突を検出 → 自動 abort して隔離"
    git rebase --abort
    quarantine_branch="quarantine/rebase-conflict-${CUR_BRANCH//\//-}-$(ts)"
    git branch "$quarantine_branch" 2>/dev/null || true
    echo "🛑 HUMAN-REVIEW-REQUIRED: rebase 衝突。現状を $quarantine_branch に保全。"
    echo "   元ブランチ $CUR_BRANCH は rebase 前の状態に戻した（main 汚染なし）。"
    exit 1
    ;;

  stash-guard)
    echo "=== auto_isolate: stash-guard ==="
    if [[ -z "$(git status --porcelain)" ]]; then
      echo "✓ 未コミット変更なし（クリーン）"
      exit 0
    fi
    stash_msg="auto_isolate-stash-$(ts)"
    git stash push -u -m "$stash_msg"
    echo "✓ 未コミット変更を stash に退避: $stash_msg"
    echo "  復元: git stash pop"
    exit 0
    ;;

  quarantine)
    reason="${2:-unspecified}"
    echo "=== auto_isolate: quarantine ($reason) ==="
    q_branch="quarantine/${reason//[^a-zA-Z0-9]/-}-$(ts)"
    if [[ -n "$(git status --porcelain)" ]]; then
      git stash push -u -m "quarantine-$reason-$(ts)" >/dev/null
      git branch "$q_branch"
      git stash branch "$q_branch" >/dev/null 2>&1 || {
        # stash branch が使えない場合は隔離ブランチに pop
        git checkout "$q_branch" -q && git stash pop >/dev/null 2>&1 || true
        git add -A && git commit -q -m "quarantine: $reason" || true
        git checkout "$CUR_BRANCH" -q
      }
      echo "✓ 変更を隔離ブランチ $q_branch に退避（元ブランチはクリーン）"
    else
      echo "隔離対象の変更なし"
    fi
    echo "🛑 HUMAN-REVIEW-REQUIRED: $q_branch を人間が確認"
    exit 1
    ;;

  check-regression)
    shift
    test_cmd="$*"
    [[ -z "$test_cmd" ]] && { echo "テストコマンド未指定" >&2; exit 2; }
    echo "=== auto_isolate: check-regression: $test_cmd ==="
    if eval "$test_cmd"; then
      echo "✓ テスト pass（リグレッションなし）"
      exit 0
    fi
    echo "⚠ テスト失敗 → 隔離ブランチに退避"
    q_branch="quarantine/regression-${CUR_BRANCH//\//-}-$(ts)"
    git branch "$q_branch" 2>/dev/null || true
    echo "🛑 HUMAN-REVIEW-REQUIRED: テスト破壊。現状を $q_branch に保全。"
    echo "   原因切り分け: 自変更起因なら修正、既存 flaky なら 1 回 re-run。"
    exit 1
    ;;

  *)
    echo "usage: $0 {rebase|stash-guard|quarantine <reason>|check-regression <cmd>}" >&2
    exit 2
    ;;
esac
