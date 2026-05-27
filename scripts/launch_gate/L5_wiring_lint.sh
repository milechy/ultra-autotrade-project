#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/launch_gate/L5_wiring_lint.sh
#
# Launch Gate L5: 孤立コード (= 定義したが main.py から register されていない
# router / startup hook) の検出。
#
# 目的:
#   AutoEvacuator / CompoundRiskAssessor 等、過去に「実装したが
#   main.py / startup から register されておらず本番では動かない」事例が
#   繰り返し発生。launch 前に grep ベースで検出する。
#
# 完璧でなくてよい (過検出 OK)。launch 前に人間がレビューする前提。
#
# 検出ロジック:
#   1. backend/app/ 配下から `APIRouter(` 定義のある .py を抽出
#   2. 各ファイルで `router = APIRouter(` 等の symbol 名 (右辺の代入先) を抜く
#   3. その module path + symbol が backend/app/main.py 内で
#      include_router(<symbol_alias>) されているかを grep
#   4. されていない symbol を fail として列挙
#
# Usage:
#   bash scripts/launch_gate/L5_wiring_lint.sh
# ---------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

PROJECT_ROOT="$(gate_project_root)"
LABEL="L5 wiring"
APP_DIR="${PROJECT_ROOT}/backend/app"
MAIN_PY="${APP_DIR}/main.py"

if [[ ! -d "${APP_DIR}" ]]; then
  gate_record FAIL "${LABEL}" "backend/app/ が見つかりません: ${APP_DIR}"
  exit 1
fi
if [[ ! -f "${MAIN_PY}" ]]; then
  gate_record FAIL "${LABEL}" "backend/app/main.py が見つかりません"
  exit 1
fi

echo "--- L5 wiring lint: scan ${APP_DIR} ---"

# main.py で import alias → 元 symbol を引くマップを作る。
# パターン例:
#   from app.aave.router import router as aave_router
#   from app.aave.router import router
#
# main.py で include_router(X) されている alias の集合
# 第1引数が同一行にあるパターンと、改行して次行にあるパターンの両方を拾う。
# 例:
#   app.include_router(auth_router)
#   app.include_router(
#       allocation_router, prefix="/api/partner",
#   )
INCLUDED_ALIASES="$(
  python3 - <<'PYEOF' "${MAIN_PY}"
import re, sys
src = open(sys.argv[1], 'r', encoding='utf-8').read()
# include_router( ... ) の中身の先頭 identifier を取る
pattern = re.compile(r'include_router\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)')
seen = set()
for m in pattern.finditer(src):
    seen.add(m.group(1))
for s in sorted(seen):
    print(s)
PYEOF
)"

# main.py で import されている "module path -> alias" の対応を抽出。
# 形式: <module> <orig_symbol> <alias>
# 例:   app.aave.router router aave_router
#       app.aave.router router router   (alias なしのケース)
IMPORTS_RAW="$(grep -nE '^[[:space:]]*from[[:space:]]+app\.[A-Za-z0-9_.]+[[:space:]]+import[[:space:]]+' "${MAIN_PY}" || true)"

# router 定義のあるファイルを列挙
ROUTER_FILES="$(grep -rlE 'APIRouter\(' "${APP_DIR}" 2>/dev/null | sort -u || true)"

if [[ -z "${ROUTER_FILES}" ]]; then
  gate_record PASS "${LABEL}" "APIRouter 定義が backend/app/ 配下に無し (検出対象なし)"
  exit 0
fi

orphans=()
checked=0

while IFS= read -r f; do
  [[ -z "${f}" ]] && continue
  checked=$(( checked + 1 ))

  # symbol 名抽出: "router = APIRouter(" や "api_router = APIRouter(" 等
  symbols="$(grep -nE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*APIRouter\(' "${f}" \
    | sed -E 's/^[0-9]+:[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=.*/\1/' \
    | sort -u)"
  [[ -z "${symbols}" ]] && continue

  # module path 推定: backend/app/foo/bar.py -> app.foo.bar
  rel="${f#"${APP_DIR}"/}"
  rel="${rel%.py}"
  module="app.${rel//\//.}"

  for sym in ${symbols}; do
    # main.py の import 行から、この module+symbol が import されているか / alias は何か
    # 例: "from app.aave.router import router as aave_router"
    #     "from app.aave.router import router"
    alias_line="$(echo "${IMPORTS_RAW}" | grep -E "from[[:space:]]+${module}[[:space:]]+import[[:space:]]" || true)"

    if [[ -z "${alias_line}" ]]; then
      # main.py から一切 import されていない → 孤立疑い
      orphans+=("${module}:${sym}  (main.py から未 import)")
      continue
    fi

    # alias 解決: "import <sym> as <alias>" / "import <sym>" / "import (<sym>, ...)"
    alias_name=""
    if echo "${alias_line}" | grep -qE "import[[:space:]]+${sym}[[:space:]]+as[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)"; then
      alias_name="$(echo "${alias_line}" | sed -nE "s/.*import[[:space:]]+${sym}[[:space:]]+as[[:space:]]+([A-Za-z_][A-Za-z0-9_]*).*/\1/p" | head -n 1)"
    elif echo "${alias_line}" | grep -qE "import[[:space:]]+(\(|[^,]*\b)${sym}\b"; then
      # alias 無し import → そのまま symbol 名で使われる
      alias_name="${sym}"
    fi

    if [[ -z "${alias_name}" ]]; then
      # import 行に sym 自体が含まれていない (他 symbol のみ import) → 孤立疑い
      orphans+=("${module}:${sym}  (main.py の import に該当 symbol 不在)")
      continue
    fi

    # main.py の include_router(<alias_name>) に含まれているか
    if echo "${INCLUDED_ALIASES}" | grep -qE "^${alias_name}$"; then
      : # OK
    else
      orphans+=("${module}:${sym}  (include_router(${alias_name}) されていない)")
    fi
  done
done <<< "${ROUTER_FILES}"

echo "  scanned router files: ${checked}"
echo "  include_router 済 alias: $(echo "${INCLUDED_ALIASES}" | wc -l | tr -d ' ')"

if [[ "${#orphans[@]}" -eq 0 ]]; then
  gate_record PASS "${LABEL}" "孤立 router 検出なし (scanned=${checked})"
  exit 0
fi

echo ""
echo "  孤立疑い (over-detection 含む — 人間レビュー前提):"
for o in "${orphans[@]}"; do
  echo "    - ${o}"
done

gate_record FAIL "${LABEL}" "孤立 router 疑い ${#orphans[@]} 件 (scanned=${checked})"
exit 1
