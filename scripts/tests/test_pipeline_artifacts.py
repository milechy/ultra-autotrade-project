"""scripts/tests/test_pipeline_artifacts.py — パイプライン補助スクリプト設定の検証テスト。

対象:
  1. repomix.config.json       — JSON 有効性・セキュリティパターン・security設定・output設定
  2. scripts/skillopt_config.json — JSON 有効性・safety設定・output_suffix・targets件数・target実在
  3. スクリプト存在と実行権限    — 各 .sh の X_OK / run_skillopt.py の存在
  4. run_skillopt.py --dry-run  — 終了コード 0 を確認（API 不要）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# リポジトリルート: scripts/tests/ の 2 階層上
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. repomix.config.json
# ---------------------------------------------------------------------------


def test_repomix_config_valid_json() -> None:
    """repomix.config.json が有効な JSON であること。"""
    config_path = REPO_ROOT / "repomix.config.json"
    assert config_path.exists(), f"repomix.config.json が見つからない: {config_path}"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)  # 無効なら json.JSONDecodeError
    assert isinstance(data, dict), "repomix.config.json のトップレベルは object であること"


def test_repomix_config_security_patterns() -> None:
    """ignore.customPatterns に必要なセキュリティパターンが含まれること。"""
    config_path = REPO_ROOT / "repomix.config.json"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    patterns: list[str] = data.get("ignore", {}).get("customPatterns", [])
    required = ["**/.env", "**/.env.*", "**/*.key", "**/*.pem"]
    for pat in required:
        assert pat in patterns, (
            f"repomix.config.json の ignore.customPatterns に '{pat}' が含まれていない"
        )


def test_repomix_config_security_check_enabled() -> None:
    """security.enableSecurityCheck が true であること。"""
    config_path = REPO_ROOT / "repomix.config.json"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("security", {}).get("enableSecurityCheck") is True, (
        "repomix.config.json の security.enableSecurityCheck が true でない"
    )


def test_repomix_config_output_style_xml() -> None:
    """output.style が 'xml' であること。"""
    config_path = REPO_ROOT / "repomix.config.json"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("output", {}).get("style") == "xml", (
        "repomix.config.json の output.style が 'xml' でない"
    )


# ---------------------------------------------------------------------------
# 2. scripts/skillopt_config.json
# ---------------------------------------------------------------------------


def test_skillopt_config_valid_json() -> None:
    """scripts/skillopt_config.json が有効な JSON であること。"""
    config_path = REPO_ROOT / "scripts" / "skillopt_config.json"
    assert config_path.exists(), f"skillopt_config.json が見つからない: {config_path}"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "skillopt_config.json のトップレベルは object であること"


def test_skillopt_config_never_overwrite_originals() -> None:
    """safety.never_overwrite_originals が true であること。"""
    config_path = REPO_ROOT / "scripts" / "skillopt_config.json"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("safety", {}).get("never_overwrite_originals") is True, (
        "skillopt_config.json の safety.never_overwrite_originals が true でない"
    )


def test_skillopt_config_output_suffix() -> None:
    """output_suffix が '.md' で終わり、かつ '.md' 単体でないこと。"""
    config_path = REPO_ROOT / "scripts" / "skillopt_config.json"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    suffix = data.get("output_suffix", "")
    assert suffix.endswith(".md"), (
        f"skillopt_config.json の output_suffix が '.md' で終わっていない: {suffix!r}"
    )
    assert suffix != ".md", (
        "skillopt_config.json の output_suffix が '.md' 単体は不正（例: '.optimized.md' を期待）"
    )


def test_skillopt_config_targets_count() -> None:
    """targets が 4 件であること。"""
    config_path = REPO_ROOT / "scripts" / "skillopt_config.json"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    targets = data.get("targets", [])
    assert len(targets) == 4, (
        f"skillopt_config.json の targets は 4 件を期待、実際: {len(targets)} 件"
    )


def test_skillopt_config_targets_paths_exist() -> None:
    """各 target の path が実在するファイルであること（リポジトリルート基準）。"""
    config_path = REPO_ROOT / "scripts" / "skillopt_config.json"
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    for target in data.get("targets", []):
        path_str = target.get("path", "")
        full_path = REPO_ROOT / path_str
        assert full_path.exists(), (
            f"skillopt_config.json の target path が存在しない: {path_str} → {full_path}"
        )
        assert full_path.is_file(), (
            f"skillopt_config.json の target path はファイルであること: {path_str}"
        )


# ---------------------------------------------------------------------------
# 3. スクリプト存在と実行権限
# ---------------------------------------------------------------------------


def test_run_repomix_sh_exists_and_executable() -> None:
    """scripts/run_repomix.sh が存在し実行可能であること。"""
    path = REPO_ROOT / "scripts" / "run_repomix.sh"
    assert path.exists(), f"run_repomix.sh が存在しない: {path}"
    assert os.access(path, os.X_OK), f"run_repomix.sh に実行権限がない: {path}"


def test_run_skillspector_sh_exists_and_executable() -> None:
    """scripts/run_skillspector.sh が存在し実行可能であること。"""
    path = REPO_ROOT / "scripts" / "run_skillspector.sh"
    assert path.exists(), f"run_skillspector.sh が存在しない: {path}"
    assert os.access(path, os.X_OK), f"run_skillspector.sh に実行権限がない: {path}"


def test_run_code_review_sh_exists_and_executable() -> None:
    """scripts/run_code_review.sh が存在し実行可能であること。"""
    path = REPO_ROOT / "scripts" / "run_code_review.sh"
    assert path.exists(), f"run_code_review.sh が存在しない: {path}"
    assert os.access(path, os.X_OK), f"run_code_review.sh に実行権限がない: {path}"


def test_auto_isolate_sh_exists_and_executable() -> None:
    """scripts/auto_isolate.sh が存在し実行可能であること。"""
    path = REPO_ROOT / "scripts" / "auto_isolate.sh"
    assert path.exists(), f"auto_isolate.sh が存在しない: {path}"
    assert os.access(path, os.X_OK), f"auto_isolate.sh に実行権限がない: {path}"


def test_run_skillopt_py_exists() -> None:
    """scripts/run_skillopt.py が存在すること。"""
    path = REPO_ROOT / "scripts" / "run_skillopt.py"
    assert path.exists(), f"run_skillopt.py が存在しない: {path}"
    assert path.is_file(), f"run_skillopt.py はファイルであること: {path}"


# ---------------------------------------------------------------------------
# 4. run_skillopt.py --dry-run が exit 0 を返す
# ---------------------------------------------------------------------------


def test_run_skillopt_dry_run_exits_zero() -> None:
    """scripts/run_skillopt.py --dry-run が exit code 0 で終了すること（API 不要）。"""
    script = REPO_ROOT / "scripts" / "run_skillopt.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"run_skillopt.py --dry-run が exit 0 でなかった (returncode={result.returncode})\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
