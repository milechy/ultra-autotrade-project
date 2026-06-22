#!/usr/bin/env bash
# check_no_committed_env_files.sh — 実 .env ファイルが git に commit されていないか検証する。
#
# 許可: .env.*.example テンプレートのみ commit 可。
# 禁止: 実 env ファイル (.env / .env.production / .env.staging / .env.staging-new /
#        .env.*.bak / .env.*.backup.* 等) は .gitignore 対象で commit 禁止
#        (Security Rule 1 = secrets を commit しない / 環境分離)。
#
# 旧 env ファイル (例: 非推奨の .env.staging 単独名) が誤って tracked になった場合も
# 本チェックで検出される。CI (env-separation-check) から呼ばれ、ローカルでも実行可能。
#
# Asana 1214696986457078 (.env 旧ファイル削除 + 検知 CI)

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# git 管理下の実 .env ファイル (.example テンプレートを除く) を列挙。
# パターン: パス末尾の構成要素が .env もしくは .env<.|->... で終わり、.example で終わらないもの。
mapfile -t tracked < <(
  git ls-files \
    | grep -E '(^|/)\.env([.-][^/]*)?$' \
    | grep -vE '\.example$' \
    || true
)

if [ "${#tracked[@]}" -gt 0 ]; then
  echo "::error::実 .env ファイルが git に commit されています (.gitignore / Security Rule 1 違反):"
  printf '  - %s\n' "${tracked[@]}"
  echo "実 env ファイルは commit 禁止です。.env.*.example テンプレートのみ commit 可。"
  echo "対処: git rm --cached <file> で追跡解除し、.gitignore を確認してください。"
  exit 1
fi

echo "✅ 実 .env ファイルの commit なし (.env.*.example テンプレートのみ tracked)"
