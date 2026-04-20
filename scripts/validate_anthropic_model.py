#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# scripts/validate_anthropic_model.py
#
# CI検証スクリプト: Anthropic Claude モデル名の整合性チェック
#
# 検証内容:
#   (a) .env.*.example の AI_CLAUDE_MODEL / AI_FALLBACK_MODEL が許可リストに含まれるか
#   (b) backend/app/**/*.py に非推奨モデル名がハードコードされていないか
#       (backend/app/ai/config.py は許可: 定数定義が必要なため)
#
# 許可リストは backend/app/ai/config.py の VALID_CLAUDE_MODELS / DEPRECATED_CLAUDE_MODELS と同期。
# 実行: python scripts/validate_anthropic_model.py
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Single source of truth: backend/app/ai/config.py と同期すること
# ---------------------------------------------------------------------------
VALID_CLAUDE_MODELS: list[str] = [
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6-20250929",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
]

DEPRECATED_CLAUDE_MODELS: list[str] = [
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-latest",
    "claude-3-opus-20240229",
]

_MODEL_VAR_RE = re.compile(r"^(AI_CLAUDE_MODEL|AI_FALLBACK_MODEL)=(.+)")
# Matches string literals like "claude-xxx" or 'claude-xxx'
_HARDCODE_RE = re.compile(r"""['"](claude-[a-z0-9.-]+)['"]""")

# config.py is the canonical definition file; skip it for hardcode check
_ALLOWLISTED_FILES = {"config.py"}


def check_env_examples(root: Path) -> list[str]:
    """Check .env.*.example files for deprecated model values."""
    errors: list[str] = []
    for env_file in sorted(root.glob(".env.*.example")):
        for line in env_file.read_text().splitlines():
            m = _MODEL_VAR_RE.match(line.strip())
            if not m:
                continue
            var_name = m.group(1)
            value = m.group(2).strip("'\"").strip()
            if value.startswith("<") or value.startswith("#"):
                continue  # placeholder, skip
            if value in DEPRECATED_CLAUDE_MODELS:
                errors.append(
                    f"  ❌ {env_file.name}: {var_name}={value!r} は非推奨モデルです"
                )
            elif value not in VALID_CLAUDE_MODELS:
                errors.append(
                    f"  ⚠️  {env_file.name}: {var_name}={value!r} が許可リストにありません"
                )
    return errors


def check_hardcoded_deprecated(root: Path) -> list[str]:
    """Scan backend/app/**/*.py for hardcoded deprecated model strings."""
    errors: list[str] = []
    backend_app = root / "backend" / "app"
    if not backend_app.exists():
        return errors

    for py_file in sorted(backend_app.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        if py_file.name in _ALLOWLISTED_FILES:
            continue
        for lineno, line in enumerate(py_file.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for m in _HARDCODE_RE.finditer(line):
                model_name = m.group(1)
                if model_name in DEPRECATED_CLAUDE_MODELS:
                    rel = py_file.relative_to(root)
                    errors.append(
                        f"  ❌ {rel}:{lineno}: 非推奨モデルがハードコード: {model_name!r}"
                    )
    return errors


def main() -> int:
    root = Path(__file__).parent.parent

    print("=== Anthropic Claude モデル名検証 ===\n")

    env_errors = check_env_examples(root)
    hardcode_errors = check_hardcoded_deprecated(root)

    all_errors = env_errors + hardcode_errors

    if env_errors:
        print("【.env.*.example チェック】")
        for e in env_errors:
            print(e)
        print()
    else:
        print("✅ .env.*.example チェック: 問題なし")

    if hardcode_errors:
        print("\n【ハードコード非推奨モデル チェック】")
        for e in hardcode_errors:
            print(e)
        print()
    else:
        print("✅ ハードコード非推奨モデル チェック: 問題なし")

    if all_errors:
        print(f"\n❌ 検証失敗: {len(all_errors)} 件のエラー")
        print(f"   有効なモデル名: {VALID_CLAUDE_MODELS}")
        return 1

    print("\n✅ 全チェック通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
