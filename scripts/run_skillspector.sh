#!/usr/bin/env bash
# scripts/run_skillspector.sh — .claude/agents/*.md と .claude/skills/**/SKILL.md を
# NVIDIA SkillSpector でセキュリティスキャンする
#
# 用途:
#   AIエージェント/スキル定義ファイルに対するプロンプトインジェクション・権限昇格・
#   データ流出パターンを検出する。外部スキルを導入する前の審査（金融システムの安全性強化）。
#
# 使い方:
#   ./scripts/run_skillspector.sh           # スキャンして結果表示（人間確認用）
#   ./scripts/run_skillspector.sh --ci      # CI モード: HIGH/CRITICAL 検出で exit 1
#
# 前提: uv（無ければ自動 install を試みる）/ git / make
# 参考: https://github.com/NVIDIA/skillspector （Apache-2.0）
#
# 設計メモ: SkillSpector の README は「脆弱性検出時の exit code」を明記していないため、
#   本スクリプトは exit code に依存せず JSON 出力を jq でパースして severity を判定する。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

CI_MODE="false"
[[ "${1:-}" == "--ci" ]] && CI_MODE="true"

SKILLSPECTOR_DIR="${SKILLSPECTOR_DIR:-/tmp/skillspector}"
REPORT_DIR="${REPORT_DIR:-/tmp/skillspector-reports}"
FAIL_SEVERITIES="${FAIL_SEVERITIES:-HIGH CRITICAL}"

mkdir -p "$REPORT_DIR"

# ---- 1. SkillSpector の準備（uv + clone + make install）----
ensure_skillspector() {
  if command -v skillspector >/dev/null 2>&1; then
    echo "skillspector: already on PATH"
    return
  fi
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv が無いため install します..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  if [[ ! -d "$SKILLSPECTOR_DIR/.git" ]]; then
    # SKILLSPECTOR_REF を指定すればタグ/SHA 固定可（サプライチェーン対策 / 監査 MINOR-2）
    git clone --depth 1 ${SKILLSPECTOR_REF:+--branch "$SKILLSPECTOR_REF"} \
      https://github.com/NVIDIA/skillspector.git "$SKILLSPECTOR_DIR"
  fi
  # 入れ替わり検知のため取得した commit を記録（監査 MINOR-2）
  echo "skillspector commit: $(git -C "$SKILLSPECTOR_DIR" rev-parse HEAD)"
  ( cd "$SKILLSPECTOR_DIR" && uv venv .venv && . .venv/bin/activate && make install )
  # make install 後、venv 内の skillspector を使う
  export PATH="$SKILLSPECTOR_DIR/.venv/bin:$PATH"
}

# ---- 2. スキャン対象の収集 ----
collect_targets() {
  # .claude/agents/*.md（個別ファイル）と .claude/skills/*/（ディレクトリ単位）
  find .claude/agents -maxdepth 1 -name '*.md' 2>/dev/null || true
  find .claude/skills -maxdepth 1 -mindepth 1 -type d 2>/dev/null || true
}

# ---- 3. 実行 ----
ensure_skillspector

FOUND_BLOCKING=0
SCAN_COUNT=0

while IFS= read -r target; do
  [[ -z "$target" ]] && continue
  SCAN_COUNT=$((SCAN_COUNT + 1))
  safe_name="$(echo "$target" | tr '/ ' '__')"
  json_out="$REPORT_DIR/${safe_name}.json"

  echo "=== scan: $target ==="
  # 終了コードに依存しない（|| true）。判定は JSON パースで行う
  skillspector scan "$target" --format json --output "$json_out" || true

  if [[ -f "$json_out" ]] && command -v jq >/dev/null 2>&1; then
    # JSON 内のあらゆる severity フィールドを拾う（スキーマ非依存の防御的パース）
    sev_list="$(jq -r '.. | objects | (.severity? // .level? // empty)' "$json_out" 2>/dev/null | tr '[:lower:]' '[:upper:]' | sort -u || true)"
    echo "  検出 severity: ${sev_list:-なし}"
    for fail_sev in $FAIL_SEVERITIES; do
      if echo "$sev_list" | grep -qw "$fail_sev"; then
        echo "  🔴 $fail_sev を検出: $target"
        FOUND_BLOCKING=$((FOUND_BLOCKING + 1))
      fi
    done
  else
    echo "  (jq 不在 or JSON 未生成 — 出力 $json_out を人間が確認すること)"
  fi
done < <(collect_targets)

echo ""
echo "========================================="
echo " skillspector: $SCAN_COUNT 対象スキャン / blocking $FOUND_BLOCKING 件"
echo " レポート: $REPORT_DIR/"
echo "========================================="

if [[ "$CI_MODE" == "true" && "$FOUND_BLOCKING" -gt 0 ]]; then
  echo "CI: HIGH/CRITICAL 検出のため fail" >&2
  exit 1
fi
exit 0
