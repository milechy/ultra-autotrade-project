# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""オプティマイザーテスト共有フィクスチャ。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.optimizer.allocator import PortfolioAllocator
from app.ai.optimizer.net_benefit import ExpectedNetBenefitCalculator
from app.ai.optimizer.schemas import Protocol, StrategyCandidate
from app.ai.optimizer.strategy_scorer import StrategyScorer


@pytest.fixture
def sample_candidates() -> list[StrategyCandidate]:
    """5つのプロトコル候補リスト（テスト用固定値）。"""
    return [
        StrategyCandidate(
            protocol=Protocol.AAVE,
            asset="USDC",
            expected_apy=Decimal("4.5"),
            gas_cost_usd=Decimal("2.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.05"),
            liquidity_available=Decimal("1000000000"),
        ),
        StrategyCandidate(
            protocol=Protocol.LIDO,
            asset="ETH",
            expected_apy=Decimal("3.5"),
            gas_cost_usd=Decimal("5.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.15"),
            liquidity_available=Decimal("500000000"),
        ),
        StrategyCandidate(
            protocol=Protocol.LIDO_AAVE,
            asset="stETH",
            expected_apy=Decimal("5.0"),
            gas_cost_usd=Decimal("8.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.20"),
            liquidity_available=Decimal("500000000"),
        ),
        StrategyCandidate(
            protocol=Protocol.PENDLE_PT,
            asset="stETH",
            expected_apy=Decimal("5.2"),
            gas_cost_usd=Decimal("10.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.10"),
            liquidity_available=Decimal("100000000"),
            maturity_days=30,
        ),
        StrategyCandidate(
            protocol=Protocol.PENDLE_YT,
            asset="stETH",
            expected_apy=Decimal("8.0"),
            gas_cost_usd=Decimal("10.0"),
            bridge_cost_usd=Decimal("0"),
            risk_penalty=Decimal("0.30"),
            liquidity_available=Decimal("100000000"),
            maturity_days=30,
        ),
    ]


@pytest.fixture
def calculator() -> ExpectedNetBenefitCalculator:
    """ExpectedNetBenefitCalculator インスタンス。"""
    return ExpectedNetBenefitCalculator()


@pytest.fixture
def scorer() -> StrategyScorer:
    """StrategyScorer インスタンス。"""
    return StrategyScorer()


@pytest.fixture
def allocator() -> PortfolioAllocator:
    """PortfolioAllocator インスタンス。"""
    return PortfolioAllocator()
