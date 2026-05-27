#!/usr/bin/env bash
# Ultra AutoTrade — 配線 lint (include_router 漏れ検出) CI guard
#
# 目的:
#   backend/app/ 配下で `APIRouter(...)` で生成された router 変数 (router, *_router など) が、
#   backend/app/main.py で `app.include_router(<name>)` されているかを検証する。
#
#   Asana 1215151958676195 / [LAUNCH-GATE-B]
#   memory: project-recurring-drift-patterns
#     - AutoEvacuator + CompoundRiskAssessor 配線漏れ
#     - PR #128 lint fail
#     - check_env_separation.sh の Phase 1 例外ロジック漏れ
#
# 終了コード:
#   0: OK
#   1: FAIL (孤立 router 検出)
#
# 補足:
#   - WIRING_LINT_ALLOWLIST="app.foo.router:router app.bar.x:admin_router"
#     のように "module:symbol" 形式 (space 区切り) で除外可能。
#   - サブルーター (親 router.py で include_router される構造) は自動的に除外。
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "${REPO_ROOT}"

exec python3 - "$@" <<'PYEOF'
import os
import re
import sys
from pathlib import Path

MAIN_PY = Path("backend/app/main.py")
APP_DIR = Path("backend/app")

allowlist_env = os.environ.get("WIRING_LINT_ALLOWLIST", "")
ALLOWLIST = set(filter(None, allowlist_env.split()))

if not MAIN_PY.is_file():
    print(f"❌ FAIL: {MAIN_PY} が見つかりません")
    sys.exit(1)

main_src = MAIN_PY.read_text(encoding="utf-8")

# 1. main.py の import を (module, orig_symbol, local_name) 三組として抽出する。
#    対応パターン (single-line import のみ。multi-line/括弧 import は除外):
#      from app.foo.bar import router
#      from app.foo.bar import router as foo_router
#      from app.foo.bar import api_router as foo_api_router
#      from app.foo.bar import router, admin_router  (分割)
#      from app.foo.bar import (router as foo_router,)
import_pat = re.compile(
    r"^from\s+(?P<module>app\.[A-Za-z0-9_.]+)\s+import\s+(?P<rest>.+?)$",
    re.MULTILINE,
)

# 括弧形式の multi-line import も取り込む簡易処理
def expand_multiline_imports(src: str) -> str:
    out = []
    i = 0
    lines = src.split("\n")
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^from\s+(app\.[A-Za-z0-9_.]+)\s+import\s+\((.*)$", line)
        if m:
            module = m.group(1)
            rest = m.group(2)
            collected = [rest]
            j = i + 1
            while j < len(lines) and ")" not in lines[j]:
                collected.append(lines[j])
                j += 1
            if j < len(lines):
                # 最後の行で ) 直前まで取り込む
                tail = lines[j].split(")")[0]
                collected.append(tail)
                i = j
            joined = " ".join(c.strip() for c in collected)
            joined = joined.replace(",", " , ")
            out.append(f"from {module} import {joined}")
        else:
            out.append(line)
        i += 1
    return "\n".join(out)

main_src_flat = expand_multiline_imports(main_src)

# (module, orig, local) のリスト
imports = []
for m in import_pat.finditer(main_src_flat):
    module = m.group("module")
    rest = m.group("rest").strip()
    # 末尾のコメント除去
    rest = re.split(r"\s+#", rest, maxsplit=1)[0].strip()
    # 末尾の括弧を除去
    rest = rest.strip("()").strip()
    # カンマ区切りで複数 import に対応
    for part in rest.split(","):
        part = part.strip()
        if not part:
            continue
        as_m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s+as\s+([A-Za-z_][A-Za-z0-9_]*)$", part)
        if as_m:
            orig, local = as_m.group(1), as_m.group(2)
        else:
            simple_m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)$", part)
            if simple_m:
                orig = local = simple_m.group(1)
            else:
                continue
        imports.append((module, orig, local))

# 2. app.include_router(<local>) の local 集合
included_local = set(
    re.findall(r"app\.include_router\(\s*([A-Za-z_][A-Za-z0-9_]*)", main_src)
)

# 3. backend/app/ 配下で APIRouter() 定義を探索
router_def_pat = re.compile(
    r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*APIRouter\(",
    re.MULTILINE,
)

orphans = []
checked = 0

for py_file in sorted(APP_DIR.rglob("*.py")):
    if py_file == MAIN_PY:
        continue
    if "__pycache__" in py_file.parts:
        continue
    text = py_file.read_text(encoding="utf-8", errors="ignore")
    matches = router_def_pat.findall(text)
    if not matches:
        continue

    # module path 推定:
    #   backend/app/foo/bar.py     -> app.foo.bar
    #   backend/app/foo/router.py  -> app.foo.router  (かつ親 app.foo の re-export 候補)
    rel = py_file.relative_to(Path("backend"))
    parts = list(rel.with_suffix("").parts)  # ['app', 'foo', 'bar']
    module = ".".join(parts)
    parent_module = ".".join(parts[:-1]) if len(parts) > 1 else None

    # サブルーター parent 経由配線の検出:
    # 同ディレクトリの router.py (=自分以外) で `from .<this_basename> import` や
    # include_router が行われている場合、parent 経由配線とみなす。
    parent_router_py = py_file.parent / "router.py"
    parent_handles_this = False
    if py_file != parent_router_py and parent_router_py.is_file():
        parent_text = parent_router_py.read_text(encoding="utf-8", errors="ignore")
        if "include_router(" in parent_text:
            parent_handles_this = True
        if re.search(rf"from\s+\.{re.escape(py_file.stem)}\s+import", parent_text):
            parent_handles_this = True

    # ファイル自身に include_router( がある = 親 router で他のサブを束ねている
    self_aggregates = "include_router(" in text

    for symbol in matches:
        checked += 1
        key = f"{module}:{symbol}"
        key_parent = f"{parent_module}:{symbol}" if parent_module else None

        if key in ALLOWLIST or (key_parent and key_parent in ALLOWLIST):
            print(f"⚠️  allowlisted: {py_file}::{symbol}")
            continue

        # main.py の import が (module, symbol) または (parent_module, symbol) を含むか
        matching_locals = [
            local for (mod, orig, local) in imports
            if orig == symbol and (mod == module or (parent_module and mod == parent_module))
        ]

        if matching_locals:
            # いずれかの local 名が include_router されていれば OK
            if any(local in included_local for local in matching_locals):
                continue
            # import 済だが include 漏れ
            orphans.append((str(py_file), symbol, f"imported as {matching_locals} but not include_router'd"))
            continue

        # import すらされていない
        # 例外: 親 router 経由配線
        if parent_handles_this or self_aggregates:
            continue

        orphans.append((str(py_file), symbol, "not imported in main.py"))

if orphans:
    print(f"❌ FAIL: 配線漏れ router を検出しました ({len(orphans)} 件 / {checked} checked)")
    print()
    for f, sym, reason in orphans:
        print(f"  - {f}::{sym} ({reason})")
    print()
    print("対処:")
    print(f"  1. {MAIN_PY} に `from <module> import {{symbol}} as <local>_router` を追加")
    print("  2. `app.include_router(<local>_router, prefix=..., tags=[...])` を追加")
    print("  3. 意図的な孤立 (廃止予定 / サブルーター parent 経由 等) の場合は")
    print('     WIRING_LINT_ALLOWLIST="app.foo.router:router app.bar:admin_router" を設定')
    sys.exit(1)

print(f"✅ 配線 lint OK: 孤立 router なし ({checked} router defs checked)")
PYEOF
