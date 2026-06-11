#!/usr/bin/env bash
# scripts/run_repomix.sh — リポジトリを単一の AI フレンドリーファイルにパックする
#
# 用途:
#   - Gate 5（孤立コード検出）の前処理: backend/ 全体を 1 ファイルに圧縮し、
#     「実装されているが呼ばれていない」孤立コードを Claude に一括で渡せるようにする
#   - 並列レーン起動時のコンテキスト準備
#
# 使い方:
#   ./scripts/run_repomix.sh                # backend/ をパック（既定）
#   ./scripts/run_repomix.sh backend/app/aave   # 特定サブツリーのみ
#   ./scripts/run_repomix.sh .              # リポジトリ全体
#
# 出力: repomix-output.xml（リポジトリ root / .gitignore 済み）
#
# 前提: node / npx（dev VPS は node v22）。repomix は npx 経由で取得するため事前 install 不要。
# 除外設定: repomix.config.json（.env* / *.key / *.pem / node_modules / __pycache__ / migrations 等）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

TARGET="${1:-backend}"
OUTPUT_FILE="repomix-output.xml"

echo "========================================="
echo " repomix pack: $TARGET"
echo " config: repomix.config.json"
echo "========================================="

# --include で対象を絞る（config の ignore はそのまま効く）
npx -y repomix@latest --config repomix.config.json --include "${TARGET}/**"

if [[ -f "$OUTPUT_FILE" ]]; then
  echo ""
  echo "========================================="
  echo " 出力: $PROJECT_ROOT/$OUTPUT_FILE"
  SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
  echo " サイズ: $SIZE"
  echo "========================================="
  echo ""
  echo "次の手順（Gate 5 / 孤立コード検出）:"
  echo "  1. Claude に $OUTPUT_FILE を渡す"
  echo "  2. docs/ops/orphan_detection.md の検出プロンプトを実行"
  echo "  3. 重点: backend/app/aave/, automation/, protocols/, ai/"
else
  echo "ERROR: $OUTPUT_FILE が生成されませんでした" >&2
  exit 1
fi
