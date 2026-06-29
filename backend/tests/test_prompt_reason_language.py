# Copyright (c) Ultra AutoTrade. All rights reserved.
"""AI判定プロンプトの reason フィールドが日本語出力を指示しているかの回帰テスト。

V3〜V6（英語システムプロンプト）は以前 reason の言語指定が無く LLM が英語で
出力していた。日本語ユーザー向けに reason を日本語で出させるため、各版に
「判断根拠を必ず日本語で」を明記した。本テストはその退行を防ぐ。
"""

import pytest

from app.ai.prompts import PROMPT_REGISTRY


@pytest.mark.parametrize("version", ["v3", "v4", "v5", "v6"])
def test_reason_field_requires_japanese(version: str) -> None:
    """V3〜V6 の system プロンプトが reason の日本語記述を指示している。"""
    system = PROMPT_REGISTRY[version].system_prompt
    assert "日本語" in system, f"{version}: reason の日本語指定が無い"
    # 旧来の言語非指定ヒントが残っていないこと
    assert "Brief explanation referencing" not in system, (
        f"{version}: 言語非指定の旧 reason ヒントが残存している"
    )
