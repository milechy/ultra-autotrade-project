# Copyright (c) Ultra AutoTrade. All rights reserved.
"""AI オプティマイザー FastAPI ルーターのテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# FastAPI TestClient のセットアップ
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.optimizer.router import router
from app.ai.optimizer.schemas import (
    AllocationEntry,
    AllocationRecommendation,
    NetBenefitResult,
    Protocol,
    Recommendation,
    StrategyComparison,
)

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


def _make_net_benefit_result(
    protocol: Protocol = Protocol.AAVE,
    asset: str = "USDC",
    net_benefit: str = "40.0",
    rank: int = 1,
    recommendation: Recommendation = Recommendation.BUY,
) -> NetBenefitResult:
    """テスト用 NetBenefitResult を生成する。"""
    return NetBenefitResult(
        protocol=protocol,
        asset=asset,
        expected_net_benefit=Decimal(net_benefit),
        gross_yield=Decimal("45.0"),
        total_cost=Decimal("5.0"),
        risk_adjusted_yield=Decimal("40.0"),
        expected_apy=Decimal("4.5"),
        rank=rank,
        recommendation=recommendation,
    )


def _make_sample_comparison() -> StrategyComparison:
    """テスト用 StrategyComparison を生成する。"""
    recommended = _make_net_benefit_result()
    idle = _make_net_benefit_result(
        protocol=Protocol.IDLE,
        asset="CASH",
        net_benefit="0",
        rank=2,
        recommendation=Recommendation.HOLD,
    )
    return StrategyComparison(
        candidates=[recommended, idle],
        recommended=recommended,
        idle_benefit=Decimal("0"),
        comparison_timestamp="2026-01-01T00:00:00",
    )


def _make_sample_allocation() -> AllocationRecommendation:
    """テスト用 AllocationRecommendation を生成する。"""
    entries = [
        AllocationEntry(
            protocol=Protocol.AAVE,
            asset="USDC",
            allocation_pct=Decimal("95"),
            amount_usd=Decimal("950"),
            expected_apy=Decimal("4.5"),
        ),
        AllocationEntry(
            protocol=Protocol.IDLE,
            asset="CASH",
            allocation_pct=Decimal("5"),
            amount_usd=Decimal("50"),
            expected_apy=Decimal("0"),
        ),
    ]
    return AllocationRecommendation(
        allocations=entries,
        total_expected_apy=Decimal("4.275"),
        total_risk_score=Decimal("5"),
        explanation="保守的配分: Aave 95%, 待機 5%",
    )


class TestRecommendEndpoint:
    """POST /api/ai/optimizer/recommend のテスト。"""

    def test_recommend_returns_200(self) -> None:
        """正常リクエストで 200 が返ること。"""
        comparison = _make_sample_comparison()
        allocation = _make_sample_allocation()
        report = "テストレポート"

        with (
            patch("app.ai.optimizer.router.StrategyComparator") as mock_comparator_cls,
            patch("app.ai.optimizer.router.PortfolioAllocator") as mock_allocator_cls,
        ):
            mock_comparator = MagicMock()
            mock_comparator.compare.return_value = comparison
            mock_comparator.generate_report.return_value = report
            mock_comparator_cls.return_value = mock_comparator

            mock_allocator = MagicMock()
            mock_allocator.allocate = AsyncMock(return_value=allocation)
            mock_allocator_cls.return_value = mock_allocator

            response = _client.post(
                "/api/ai/optimizer/recommend",
                json={
                    "investment_usd": "1000",
                    "risk_mode": "conservative",
                    "holding_days": 30,
                },
            )

        assert response.status_code == 200

    def test_recommend_returns_optimizer_response_structure(self) -> None:
        """レスポンスが OptimizerResponse の構造を持つこと。"""
        comparison = _make_sample_comparison()
        allocation = _make_sample_allocation()
        report = "テストレポート本文"

        with (
            patch("app.ai.optimizer.router.StrategyComparator") as mock_comparator_cls,
            patch("app.ai.optimizer.router.PortfolioAllocator") as mock_allocator_cls,
        ):
            mock_comparator = MagicMock()
            mock_comparator.compare.return_value = comparison
            mock_comparator.generate_report.return_value = report
            mock_comparator_cls.return_value = mock_comparator

            mock_allocator = MagicMock()
            mock_allocator.allocate = AsyncMock(return_value=allocation)
            mock_allocator_cls.return_value = mock_allocator

            response = _client.post(
                "/api/ai/optimizer/recommend",
                json={
                    "investment_usd": "1000",
                    "risk_mode": "conservative",
                    "holding_days": 30,
                },
            )

        data = response.json()
        assert "comparison" in data
        assert "allocation" in data
        assert "report" in data

    def test_recommend_value_error_returns_422(self) -> None:
        """ValueError 発生時に 422 を返すこと。"""
        with patch("app.ai.optimizer.router.StrategyComparator") as mock_comparator_cls:
            mock_comparator = MagicMock()
            mock_comparator.compare.side_effect = ValueError("無効な投資額")
            mock_comparator_cls.return_value = mock_comparator

            response = _client.post(
                "/api/ai/optimizer/recommend",
                json={
                    "investment_usd": "-100",
                    "risk_mode": "conservative",
                    "holding_days": 30,
                },
            )

        assert response.status_code == 422

    def test_recommend_unexpected_exception_returns_503(self) -> None:
        """予期しない例外発生時に 503 を返すこと。"""
        with patch("app.ai.optimizer.router.StrategyComparator") as mock_comparator_cls:
            mock_comparator = MagicMock()
            mock_comparator.compare.side_effect = RuntimeError("内部エラー")
            mock_comparator_cls.return_value = mock_comparator

            response = _client.post(
                "/api/ai/optimizer/recommend",
                json={
                    "investment_usd": "1000",
                    "risk_mode": "balanced",
                    "holding_days": 30,
                },
            )

        assert response.status_code == 503

    def test_recommend_with_balanced_risk_mode(self) -> None:
        """balanced リスクモードでリクエストが処理されること。"""
        comparison = _make_sample_comparison()
        allocation = _make_sample_allocation()

        with (
            patch("app.ai.optimizer.router.StrategyComparator") as mock_comparator_cls,
            patch("app.ai.optimizer.router.PortfolioAllocator") as mock_allocator_cls,
        ):
            mock_comparator = MagicMock()
            mock_comparator.compare.return_value = comparison
            mock_comparator.generate_report.return_value = "balanced report"
            mock_comparator_cls.return_value = mock_comparator

            mock_allocator = MagicMock()
            mock_allocator.allocate = AsyncMock(return_value=allocation)
            mock_allocator_cls.return_value = mock_allocator

            response = _client.post(
                "/api/ai/optimizer/recommend",
                json={
                    "investment_usd": "5000",
                    "risk_mode": "balanced",
                    "holding_days": 90,
                },
            )

        assert response.status_code == 200
        # compare に balanced モードが渡されること
        mock_comparator.compare.assert_called_once_with(
            investment_usd=Decimal("5000"),
            risk_mode="balanced",
            holding_days=90,
        )


class TestRecommendRiskModeLive:
    """live 経路（実 comparator）で risk_mode がランキングへ効くことの検証（レビュー M1）。

    モックを使わず実 StrategyComparator を通し、conservative と aggressive で
    pendle_yt（最高リスク）の net_benefit が変わることを HTTP レスポンスで担保する。
    """

    @staticmethod
    def _yt_net_benefit(payload: dict[str, object], risk_mode: str) -> Decimal:
        body = {
            "investment_usd": "10000",
            "risk_mode": risk_mode,
            "holding_days": 30,
        }
        response = _client.post("/api/ai/optimizer/recommend", json=body)
        assert response.status_code == 200, response.text
        candidates = response.json()["comparison"]["candidates"]
        yt = next(c for c in candidates if c["protocol"] == "pendle_yt")
        return Decimal(str(yt["expected_net_benefit"]))

    def test_conservative_yields_lower_net_benefit_than_aggressive(self) -> None:
        """conservative（高リスクペナルティ）は aggressive より YT の net_benefit が小さいこと。"""
        conservative = self._yt_net_benefit({}, "conservative")
        aggressive = self._yt_net_benefit({}, "aggressive")
        assert conservative < aggressive
