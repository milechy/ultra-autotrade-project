# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""AI オプティマイザー router のユニットテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.ai.optimizer.schemas import (
    AllocationEntry,
    AllocationRecommendation,
    NetBenefitResult,
    Protocol,
    Recommendation,
    StrategyComparison,
)


def _make_net_benefit_result(rank: int = 1) -> NetBenefitResult:
    return NetBenefitResult(
        protocol=Protocol.AAVE,
        asset="USDC",
        expected_net_benefit=Decimal("120.00"),
        gross_yield=Decimal("150.00"),
        total_cost=Decimal("30.00"),
        risk_adjusted_yield=Decimal("120.00"),
        expected_apy=Decimal("3.5"),
        rank=rank,
        recommendation=Recommendation.BUY,
    )


def _make_comparison() -> StrategyComparison:
    return StrategyComparison(
        candidates=[_make_net_benefit_result(1)],
        recommended=_make_net_benefit_result(1),
        idle_benefit=Decimal("0"),
        comparison_timestamp="2026-05-19T00:00:00+00:00",
    )


def _make_allocation() -> AllocationRecommendation:
    return AllocationRecommendation(
        allocations=[
            AllocationEntry(
                protocol=Protocol.AAVE,
                asset="USDC",
                allocation_pct=Decimal("95"),
                amount_usd=Decimal("9500"),
                expected_apy=Decimal("3.5"),
            )
        ],
        total_expected_apy=Decimal("3.325"),
        total_risk_score=Decimal("0.1"),
        explanation="conservative: AAVE 95%",
    )


@pytest.fixture()
def client() -> TestClient:
    from fastapi import FastAPI

    from app.ai.optimizer.router import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestOptimizerRouter:
    """POST /api/ai/optimizer/recommend のテスト。"""

    @patch("app.ai.optimizer.router.StrategyComparator")
    @patch("app.ai.optimizer.router.PortfolioAllocator")
    def test_recommend_conservative_200(
        self,
        mock_allocator_cls: MagicMock,
        mock_comparator_cls: MagicMock,
        client: TestClient,
    ) -> None:
        """conservative モードで 200 が返ること。"""
        mock_comparator = MagicMock()
        mock_comparator.compare_async = AsyncMock(return_value=_make_comparison())
        mock_comparator.generate_report.return_value = "レポート本文"
        mock_comparator_cls.return_value = mock_comparator

        mock_allocator = MagicMock()
        mock_allocator.allocate = AsyncMock(return_value=_make_allocation())
        mock_allocator_cls.return_value = mock_allocator

        resp = client.post(
            "/api/ai/optimizer/recommend",
            json={
                "investment_usd": "10000",
                "risk_mode": "conservative",
                "holding_days": 30,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "comparison" in body
        assert "allocation" in body
        assert "report" in body

    @patch("app.ai.optimizer.router.StrategyComparator")
    @patch("app.ai.optimizer.router.PortfolioAllocator")
    def test_recommend_aggressive_mode(
        self,
        mock_allocator_cls: MagicMock,
        mock_comparator_cls: MagicMock,
        client: TestClient,
    ) -> None:
        """aggressive モードでも 200 が返ること。"""
        mock_comparator = MagicMock()
        mock_comparator.compare_async = AsyncMock(return_value=_make_comparison())
        mock_comparator.generate_report.return_value = "aggressive report"
        mock_comparator_cls.return_value = mock_comparator

        mock_allocator = MagicMock()
        mock_allocator.allocate = AsyncMock(return_value=_make_allocation())
        mock_allocator_cls.return_value = mock_allocator

        resp = client.post(
            "/api/ai/optimizer/recommend",
            json={
                "investment_usd": "50000",
                "risk_mode": "aggressive",
                "holding_days": 90,
            },
        )
        assert resp.status_code == 200

    @patch("app.ai.optimizer.router.StrategyComparator")
    @patch("app.ai.optimizer.router.PortfolioAllocator")
    def test_recommend_passes_correct_args(
        self,
        mock_allocator_cls: MagicMock,
        mock_comparator_cls: MagicMock,
        client: TestClient,
    ) -> None:
        """compare / allocate に正しい引数が渡ること。"""
        mock_comparator = MagicMock()
        mock_comparator.compare_async = AsyncMock(return_value=_make_comparison())
        mock_comparator.generate_report.return_value = ""
        mock_comparator_cls.return_value = mock_comparator

        mock_allocator = MagicMock()
        mock_allocator.allocate = AsyncMock(return_value=_make_allocation())
        mock_allocator_cls.return_value = mock_allocator

        client.post(
            "/api/ai/optimizer/recommend",
            json={
                "investment_usd": "5000",
                "risk_mode": "balanced",
                "holding_days": 60,
            },
        )

        mock_comparator.compare_async.assert_awaited_once_with(
            investment_usd=Decimal("5000"),
            risk_mode="balanced",
            holding_days=60,
        )
        mock_allocator.allocate.assert_called_once()
        call_kwargs = mock_allocator.allocate.call_args.kwargs
        assert call_kwargs["total_usd"] == Decimal("5000")
        assert call_kwargs["risk_mode"] == "balanced"

    @patch("app.ai.optimizer.router.StrategyComparator")
    def test_recommend_503_on_exception(
        self,
        mock_comparator_cls: MagicMock,
        client: TestClient,
    ) -> None:
        """内部例外が 503 になること。"""
        mock_comparator = MagicMock()
        mock_comparator.compare_async = AsyncMock(side_effect=RuntimeError("DB接続失敗"))
        mock_comparator_cls.return_value = mock_comparator

        resp = client.post(
            "/api/ai/optimizer/recommend",
            json={
                "investment_usd": "1000",
                "risk_mode": "conservative",
                "holding_days": 30,
            },
        )
        assert resp.status_code == 503

    @patch("app.ai.optimizer.router.StrategyComparator")
    def test_recommend_422_on_value_error(
        self,
        mock_comparator_cls: MagicMock,
        client: TestClient,
    ) -> None:
        """ValueError が 422 になること。"""
        mock_comparator = MagicMock()
        mock_comparator.compare_async = AsyncMock(side_effect=ValueError("不正なリスクモード"))
        mock_comparator_cls.return_value = mock_comparator

        resp = client.post(
            "/api/ai/optimizer/recommend",
            json={
                "investment_usd": "1000",
                "risk_mode": "invalid",
                "holding_days": 30,
            },
        )
        assert resp.status_code == 422

    def test_recommend_missing_investment_usd(self, client: TestClient) -> None:
        """investment_usd 未指定で 422 になること。"""
        resp = client.post(
            "/api/ai/optimizer/recommend",
            json={"risk_mode": "conservative", "holding_days": 30},
        )
        assert resp.status_code == 422
