# Copyright (c) Ultra AutoTrade. All rights reserved.
"""POST /automation/process-news の CEX 自動発注ゲート（2026-06 CEX 裏線封鎖）。

旧実装は execution_policy=AUTO_EXECUTE をハードコードしており、内部トークンさえあれば
承認ゲートなしで exchange_service.execute_trade に到達できた。本テストは
NEWS_AUTO_EXECUTE_ENABLED により execution_policy が切り替わることを検証する。
"""

from unittest.mock import MagicMock, patch

import pytest

from app.auth.constants import ExecutionPolicy


def _fake_run_result() -> MagicMock:
    """process_pending_knowledge の戻り値スタブ（ProcessNewsResponse 構築に必要な属性）。"""
    rr = MagicMock()
    rr.errors = []
    rr.fetched_count = 0
    rr.analyzed_count = 0
    rr.traded_count = 0
    rr.skipped_count = 0
    rr.hold_count = 0
    rr.status = "no_items"
    return rr


def _call_process_news_capturing_policy() -> str:
    """process_news を呼び、process_pending_knowledge に渡る execution_policy を返す。"""
    from app.automation import automation_router as ar

    captured: dict[str, str] = {}

    def _fake_ppk(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured["execution_policy"] = kwargs["execution_policy"]
        return _fake_run_result()

    with (
        patch.object(ar, "process_pending_knowledge", side_effect=_fake_ppk),
        patch.object(ar, "KnowledgeService", MagicMock()),
        patch.object(ar, "AIService", MagicMock()),
        patch.object(ar, "get_exchange_service", MagicMock()),
    ):
        ar.process_news(dry_run=True, db=MagicMock(), monitoring_service=MagicMock(), _=None)

    return captured["execution_policy"]


def test_process_news_defaults_to_proposal_only_when_flag_unset() -> None:
    """フラグ未設定時は PROPOSAL_ONLY（発注に到達させない）。"""
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("NEWS_AUTO_EXECUTE_ENABLED", None)
        policy = _call_process_news_capturing_policy()
    assert policy == ExecutionPolicy.PROPOSAL_ONLY.value


def test_process_news_proposal_only_when_flag_false() -> None:
    """明示的に false でも PROPOSAL_ONLY。"""
    with patch.dict("os.environ", {"NEWS_AUTO_EXECUTE_ENABLED": "false"}):
        policy = _call_process_news_capturing_policy()
    assert policy == ExecutionPolicy.PROPOSAL_ONLY.value


def test_process_news_auto_execute_only_when_flag_true() -> None:
    """明示的に true のときだけ AUTO_EXECUTE。"""
    with patch.dict("os.environ", {"NEWS_AUTO_EXECUTE_ENABLED": "true"}):
        policy = _call_process_news_capturing_policy()
    assert policy == ExecutionPolicy.AUTO_EXECUTE.value


@pytest.mark.parametrize("value", ["1", "yes", "TRUE", "True"])
def test_process_news_truthy_values_enable_auto_execute(value: str) -> None:
    """true/1/yes（大文字小文字無視）で有効化。"""
    with patch.dict("os.environ", {"NEWS_AUTO_EXECUTE_ENABLED": value}):
        policy = _call_process_news_capturing_policy()
    assert policy == ExecutionPolicy.AUTO_EXECUTE.value
