# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_risk_limiter_check.py
"""check_trade_within_limits の単体テスト（v4 Phase 2-D の %クランプ下準備）。

純関数として 単一≤10% / 日次≤30% / HF≥floor を検査し、違反理由 or None を返すことを検証。
strict default（CUSTOM_LIMITER_ENABLED 未設定）= HF1.6 / single10% / daily30% を前提にする。
"""

from decimal import Decimal

import pytest

from app.aave.risk_limiter import check_trade_within_limits


@pytest.fixture(autouse=True)
def _force_strict_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    # custom limiter を無効化して strict default（10%/30%/1.6）を固定する。
    monkeypatch.delenv("CUSTOM_LIMITER_ENABLED", raising=False)


def test_within_limits_returns_none() -> None:
    # total=10000, single≤1000(10%), daily≤3000(30%)
    assert (
        check_trade_within_limits(
            amount_usd=Decimal("1000"),
            total_assets_usd=Decimal("10000"),
            daily_traded_usd=Decimal("0"),
            hf=Decimal("2.0"),
        )
        is None
    )


def test_single_trade_over_10pct_blocked() -> None:
    reason = check_trade_within_limits(
        amount_usd=Decimal("1000.01"),
        total_assets_usd=Decimal("10000"),
        daily_traded_usd=Decimal("0"),
        hf=Decimal("2.0"),
    )
    assert reason is not None and "single trade" in reason


def test_daily_over_30pct_blocked() -> None:
    # 既に 2500 執行済み + 600 = 3100 > 3000(30%)
    reason = check_trade_within_limits(
        amount_usd=Decimal("600"),
        total_assets_usd=Decimal("10000"),
        daily_traded_usd=Decimal("2500"),
        hf=Decimal("2.0"),
    )
    assert reason is not None and "daily trade" in reason


def test_hf_below_floor_blocked() -> None:
    reason = check_trade_within_limits(
        amount_usd=Decimal("1"),
        total_assets_usd=Decimal("10000"),
        daily_traded_usd=Decimal("0"),
        hf=Decimal("1.59"),
    )
    assert reason is not None and "hf" in reason


def test_hf_inf_and_none_skip_hf_check() -> None:
    # HF=inf / None は HF 判定をスキップ（借入なし等）
    assert (
        check_trade_within_limits(
            amount_usd=Decimal("100"),
            total_assets_usd=Decimal("10000"),
            daily_traded_usd=Decimal("0"),
            hf=Decimal("inf"),
        )
        is None
    )
    assert (
        check_trade_within_limits(
            amount_usd=Decimal("100"),
            total_assets_usd=Decimal("10000"),
            daily_traded_usd=Decimal("0"),
            hf=None,
        )
        is None
    )


def test_zero_or_none_total_skips_pct_check() -> None:
    # 総資産 0/None は % 判定をスキップ（絶対額上限は PolicyEngine が担保）。HF のみ評価。
    assert (
        check_trade_within_limits(
            amount_usd=Decimal("999999"),
            total_assets_usd=Decimal("0"),
            daily_traded_usd=Decimal("0"),
            hf=Decimal("2.0"),
        )
        is None
    )
    assert (
        check_trade_within_limits(
            amount_usd=Decimal("999999"),
            total_assets_usd=None,
            daily_traded_usd=Decimal("0"),
            hf=Decimal("2.0"),
        )
        is None
    )
