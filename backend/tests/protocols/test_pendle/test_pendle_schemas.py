"""Pendle Finance スキーマのユニットテスト。"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.protocols.pendle.schemas import (
    PendleMarketInfo,
    PendleMintRequest,
    PendleRedeemRequest,
)


class TestPendleMintRequest:
    def test_default_dry_run_is_true(self) -> None:
        req = PendleMintRequest(
            asset="0x" + "0" * 40,
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "1" * 40,
        )
        assert req.dry_run is True

    def test_amount_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            PendleMintRequest(
                asset="0x" + "0" * 40,
                amount=Decimal("0"),
                strategy="pt_fixed",
                market_address="0x" + "1" * 40,
            )

    def test_amount_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PendleMintRequest(
                asset="0x" + "0" * 40,
                amount=Decimal("-1.0"),
                strategy="pt_fixed",
                market_address="0x" + "1" * 40,
            )

    def test_amount_is_decimal(self) -> None:
        req = PendleMintRequest(
            asset="0x" + "0" * 40,
            amount=Decimal("0.5"),
            strategy="pt_fixed",
            market_address="0x" + "1" * 40,
        )
        assert type(req.amount) is Decimal

    def test_decimal_precision_preserved(self) -> None:
        """Decimal 精度が保たれることを確認。"""
        amount = Decimal("0.123456789012345678")
        req = PendleMintRequest(
            asset="0x" + "0" * 40,
            amount=amount,
            strategy="pt_fixed",
            market_address="0x" + "1" * 40,
        )
        assert req.amount == amount

    def test_strategy_pt_fixed_valid(self) -> None:
        req = PendleMintRequest(
            asset="0x" + "0" * 40,
            amount=Decimal("1.0"),
            strategy="pt_fixed",
            market_address="0x" + "1" * 40,
        )
        assert req.strategy == "pt_fixed"

    def test_strategy_yt_leverage_valid(self) -> None:
        req = PendleMintRequest(
            asset="0x" + "0" * 40,
            amount=Decimal("1.0"),
            strategy="yt_leverage",
            market_address="0x" + "1" * 40,
        )
        assert req.strategy == "yt_leverage"

    def test_strategy_invalid_rejected(self) -> None:
        """無効な strategy 文字列は拒否されることを確認。"""
        with pytest.raises(ValidationError):
            PendleMintRequest(
                asset="0x" + "0" * 40,
                amount=Decimal("1.0"),
                strategy="invalid_strategy",  # type: ignore[arg-type]
                market_address="0x" + "1" * 40,
            )

    def test_amount_from_string_converts_to_decimal(self) -> None:
        """文字列入力が Decimal に変換されることを確認。"""
        req = PendleMintRequest(
            asset="0x" + "0" * 40,
            amount="0.5",  # type: ignore[arg-type]
            strategy="pt_fixed",
            market_address="0x" + "1" * 40,
        )
        assert type(req.amount) is Decimal
        assert req.amount == Decimal("0.5")


class TestPendleMarketInfo:
    def test_creation_with_all_fields(self) -> None:
        maturity = datetime(2026, 6, 1, tzinfo=timezone.utc)
        info = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=maturity,
            days_to_maturity=67,
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        assert info.market_address == "0x" + "0" * 40
        assert info.underlying_asset == "stETH"
        assert info.days_to_maturity == 67

    def test_all_fields_decimal(self) -> None:
        """全ての金額フィールドが Decimal であることを確認。"""
        maturity = datetime(2026, 6, 1, tzinfo=timezone.utc)
        info = PendleMarketInfo(
            market_address="0x" + "0" * 40,
            underlying_asset="stETH",
            maturity=maturity,
            days_to_maturity=67,
            implied_apy=Decimal("5.2"),
            pt_price=Decimal("0.95"),
            yt_price=Decimal("0.05"),
            tvl_usd=Decimal("50000000"),
        )
        assert type(info.implied_apy) is Decimal
        assert type(info.pt_price) is Decimal
        assert type(info.yt_price) is Decimal
        assert type(info.tvl_usd) is Decimal


class TestPendleRedeemRequest:
    def test_token_type_pt_valid(self) -> None:
        req = PendleRedeemRequest(
            token_type="PT",
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        assert req.token_type == "PT"

    def test_token_type_yt_valid(self) -> None:
        req = PendleRedeemRequest(
            token_type="YT",
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        assert req.token_type == "YT"

    def test_token_type_invalid_rejected(self) -> None:
        """'PT' または 'YT' 以外は拒否されることを確認。"""
        with pytest.raises(ValidationError):
            PendleRedeemRequest(
                token_type="SY",  # type: ignore[arg-type]
                amount=Decimal("1.0"),
                market_address="0x" + "0" * 40,
            )

    def test_default_dry_run_is_true(self) -> None:
        req = PendleRedeemRequest(
            token_type="PT",
            amount=Decimal("1.0"),
            market_address="0x" + "0" * 40,
        )
        assert req.dry_run is True

    def test_amount_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            PendleRedeemRequest(
                token_type="PT",
                amount=Decimal("0"),
                market_address="0x" + "0" * 40,
            )
