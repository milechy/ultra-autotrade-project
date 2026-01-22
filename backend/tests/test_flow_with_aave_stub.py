# backend/tests/test_flow_with_aave_stub.py

import pytest


@pytest.mark.skip(
    reason=(
        "AI → OctoBot → Aave の統合フロー用テストの雛形。"
        "実際の統合環境が整ったタイミングで具体的なシナリオを実装する。"
    )
)
def test_full_flow_placeholder() -> None:
    """
    将来的に Notion → AI → OctoBot → Aave の一連のフローをモックで検証するための枠。

    現時点ではスキップしておき、Phase4 以降で拡充する。
    """
    assert True
