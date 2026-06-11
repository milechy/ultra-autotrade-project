#!/usr/bin/env python3
"""scripts/run_skillopt.py — SkillOpt でエージェント定義を最適化する安全ハーネス。

microsoft/SkillOpt (MIT) は agent/skill の md 定義をモデルウェイト変更なしに
テキスト空間で最適化する。本スクリプトは SkillOpt 本体の薄いラッパーで、
**核心は安全ハーネス**:

  1. 原本 `.claude/agents/*.md` を **絶対に上書きしない**（Tier S 相当）
  2. 最適化結果は `*.optimized.md` にのみ書き出す
  3. 原本との unified diff を生成し、人間が確認できる形にする
  4. 反映（原本への置き換え）は **人間承認後に手動** で行う（このスクリプトはしない）

使い方:
    python scripts/run_skillopt.py --dry-run        # 設定検証 + 計画表示のみ（API 不要）
    python scripts/run_skillopt.py                  # 最適化を実行し *.optimized.md を生成
    python scripts/run_skillopt.py --diff           # 既存の *.optimized.md と原本の diff を表示

SkillOpt 本体の正確な CLI / Python API は README に無く docs/guideline.html 参照。
そのため最適化の実呼び出し部 `_invoke_skillopt()` は、確認できた事実
（pip install skillopt / 出力 best_skill.md / Claude backend / held-out validation gate）
の範囲で実装し、未確定の引数は SKILLOPT_EXTRA_ARGS 環境変数で外から渡せるようにしている。

必要な環境変数（CI ではなく人間が手元で実行する想定）:
    ANTHROPIC_API_KEY   — Claude backend 用
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "scripts" / "skillopt_config.json"


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def validate_config(cfg: dict) -> list[str]:
    """設定と対象ファイルの実在を検証。問題のリストを返す（空なら OK）。"""
    problems: list[str] = []
    if not cfg.get("safety", {}).get("never_overwrite_originals"):
        problems.append("safety.never_overwrite_originals が true でない（原本保護が無効）")
    for t in cfg.get("targets", []):
        p = PROJECT_ROOT / t["path"]
        if not p.exists():
            problems.append(f"対象が存在しない: {t['path']}")
    suffix = cfg.get("output_suffix", "")
    if not suffix.endswith(".md") or suffix == ".md":
        problems.append(f"output_suffix が不正（*.optimized.md 想定）: {suffix!r}")
    return problems


def _invoke_skillopt(target_path: Path, out_path: Path, cfg: dict) -> bool:
    """SkillOpt 本体を呼び出して target を最適化し out_path に書き出す。

    SkillOpt の正確な引数は docs/guideline.html 参照（README 未記載）。
    確認済み事実: pip install skillopt / 出力 best_skill.md / Claude backend /
    held-out validation で strict 改善時のみ採用。
    未確定部は環境変数 SKILLOPT_EXTRA_ARGS で外部注入可能。
    """
    if shutil.which("skillopt") is None:
        print("  ERROR: skillopt が未インストール（pip install skillopt）", file=sys.stderr)
        return False

    extra = os.environ.get("SKILLOPT_EXTRA_ARGS", "").split()
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        cmd = [
            "skillopt",
            "optimize",
            "--input",
            str(target_path),
            "--backend",
            cfg.get("backend", "claude"),
            "--model",
            cfg.get("model", "claude-sonnet-4-6"),
            "--output-dir",
            str(workdir),
            *extra,
        ]
        print(f"  $ {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  ERROR: skillopt 実行失敗: {e}", file=sys.stderr)
            print("  → docs/guideline.html で引数確認 (SKILLOPT_EXTRA_ARGS)", file=sys.stderr)
            return False
        # SkillOpt の出力は best_skill.md（README 記載）
        produced = workdir / "best_skill.md"
        if not produced.exists():
            cands = list(workdir.glob("*.md"))
            if not cands:
                print("  ERROR: 最適化結果 md が生成されなかった", file=sys.stderr)
                return False
            produced = cands[0]
        shutil.copyfile(produced, out_path)
        return True


def show_diff(original: Path, optimized: Path) -> None:
    a = original.read_text(encoding="utf-8").splitlines(keepends=True)
    b = optimized.read_text(encoding="utf-8").splitlines(keepends=True)
    diff = difflib.unified_diff(a, b, fromfile=str(original), tofile=str(optimized))
    sys.stdout.writelines(diff)


def main() -> int:
    ap = argparse.ArgumentParser(description="SkillOpt 安全ハーネス（原本を上書きしない）")
    ap.add_argument("--dry-run", action="store_true", help="設定検証 + 計画表示のみ")
    ap.add_argument("--diff", action="store_true", help="既存 *.optimized.md と原本の diff 表示")
    args = ap.parse_args()

    cfg = load_config()
    problems = validate_config(cfg)
    if problems:
        print("設定/対象の問題:")
        for p in problems:
            print(f"  - {p}")
        return 1
    n_t = len(cfg["targets"])
    print(f"設定 OK: {n_t} 対象 / backend={cfg['backend']} / suffix={cfg['output_suffix']}")

    suffix = cfg["output_suffix"]

    if args.diff:
        for t in cfg["targets"]:
            orig = PROJECT_ROOT / t["path"]
            opt = Path(str(orig)[:-3] + suffix)
            if opt.exists():
                print(f"\n===== diff: {t['path']} =====")
                show_diff(orig, opt)
            else:
                print(f"(未生成) {opt}")
        return 0

    if args.dry_run:
        print("\n[dry-run] 最適化計画:")
        for t in cfg["targets"]:
            opt = Path(str(PROJECT_ROOT / t["path"])[:-3] + suffix)
            print(f"  {t['path']}  →  {opt.relative_to(PROJECT_ROOT)}  (原本は不変)")
        print("\n🛑 実最適化は ANTHROPIC_API_KEY + skillopt install 後に --dry-run なしで実行")
        print("🛑 原本への反映は人間が diff 確認後に手動（HUMAN-REVIEW-REQUIRED）")
        return 0

    # 実最適化
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY が未設定", file=sys.stderr)
        return 2

    any_fail = False
    for t in cfg["targets"]:
        orig = PROJECT_ROOT / t["path"]
        opt = Path(str(orig)[:-3] + suffix)
        print(f"\n===== optimize: {t['path']} =====")
        ok = _invoke_skillopt(orig, opt, cfg)
        if ok:
            print(f"  ✓ 出力: {opt.relative_to(PROJECT_ROOT)}（原本は不変）")
        else:
            any_fail = True

    print("\n🛑 HUMAN-REVIEW-REQUIRED: 原本への反映は手動。")
    print("   python scripts/run_skillopt.py --diff で差分確認 → 妥当なら手動で原本を置き換える。")
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
