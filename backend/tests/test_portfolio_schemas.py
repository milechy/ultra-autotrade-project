# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_portfolio_schemas.py
"""ポートフォリオスキーマの HF infinity cap バリデーションテスト。"""

from datetime import datetime, timezone
from decimal import Decimal

from app.portfolio.schemas import (
    PortfolioCurrentResponse,
    PortfolioLiveResponse,
    PortfolioSnapshotCreate,
    PortfolioSnapshotResponse,
)

_INF = Decimal("Infinity")
_NOW = datetime(2026, 5, 29, 0, 0, 0, tzinfo=timezone.utc)


class TestPortfolioSnapshotCreateHFCap:
    def test_inf_capped_to_999(self) -> None:
        obj = PortfolioSnapshotCreate(
            user_id=1,
            total_value_usd=Decimal("1000"),
            total_supply_usd=Decimal("1000"),
            total_borrow_usd=Decimal("0"),
            health_factor=_INF,
        )
        assert obj.health_factor == Decimal("999.0")

    def test_none_unchanged(self) -> None:
        obj = PortfolioSnapshotCreate(
            user_id=1,
            total_value_usd=Decimal("1000"),
            total_supply_usd=Decimal("1000"),
            total_borrow_usd=Decimal("0"),
            health_factor=None,
        )
        assert obj.health_factor is None

    def test_finite_unchanged(self) -> None:
        obj = PortfolioSnapshotCreate(
            user_id=1,
            total_value_usd=Decimal("1000"),
            total_supply_usd=Decimal("1000"),
            total_borrow_usd=Decimal("0"),
            health_factor=Decimal("2.5"),
        )
        assert obj.health_factor == Decimal("2.5")


class TestPortfolioSnapshotResponseHFCap:
    def test_inf_capped_to_999(self) -> None:
        obj = PortfolioSnapshotResponse.model_validate(
            {
                "id": 1,
                "user_id": 1,
                "total_value_usd": Decimal("1000"),
                "total_supply_usd": Decimal("1000"),
                "total_borrow_usd": Decimal("0"),
                "health_factor": _INF,
                "positions_json": None,
                "recorded_at": _NOW,
            }
        )
        assert obj.health_factor == Decimal("999.0")

    def test_none_unchanged(self) -> None:
        obj = PortfolioSnapshotResponse.model_validate(
            {
                "id": 1,
                "user_id": 1,
                "total_value_usd": Decimal("1000"),
                "total_supply_usd": Decimal("1000"),
                "total_borrow_usd": Decimal("0"),
                "health_factor": None,
                "positions_json": None,
                "recorded_at": _NOW,
            }
        )
        assert obj.health_factor is None


class TestPortfolioCurrentResponseHFCap:
    def test_inf_capped_to_999(self) -> None:
        obj = PortfolioCurrentResponse(health_factor=_INF)
        assert obj.health_factor == Decimal("999.0")

    def test_none_unchanged(self) -> None:
        obj = PortfolioCurrentResponse(health_factor=None)
        assert obj.health_factor is None

    def test_finite_unchanged(self) -> None:
        obj = PortfolioCurrentResponse(health_factor=Decimal("1.75"))
        assert obj.health_factor == Decimal("1.75")


class TestPortfolioLiveResponseHFCap:
    def _make(self, health_factor=None) -> PortfolioLiveResponse:
        return PortfolioLiveResponse(
            total_supply_usd=Decimal("1000"),
            total_borrow_usd=Decimal("0"),
            health_factor=health_factor,
            net_worth_usd=Decimal("1000"),
            chain="base",
            fetched_at=_NOW.isoformat(),
        )

    def test_inf_capped_to_999(self) -> None:
        obj = self._make(health_factor=_INF)
        assert obj.health_factor == Decimal("999.0")

    def test_none_unchanged(self) -> None:
        obj = self._make(health_factor=None)
        assert obj.health_factor is None

    def test_finite_unchanged(self) -> None:
        obj = self._make(health_factor=Decimal("3.14"))
        assert obj.health_factor == Decimal("3.14")

    def test_capped_value_is_finite(self) -> None:
        obj = self._make(health_factor=_INF)
        assert obj.health_factor is not None
        assert obj.health_factor.is_finite()
