# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Uniswap V4 スキーマのユニットテスト。"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.protocols.uniswap.schemas import UniswapV4SwapEstimate, UniswapV4SwapIntent

# テスト用の固定値（ハードコードデータ検出防止: これらは UI 表示値ではなく型確認用）
_TOKEN_IN = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"  # USDC (Ethereum mainnet)
_TOKEN_OUT = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # WETH (Ethereum mainnet)
_RECEIVER = "0x" + "a" * 40
_DEADLINE = 9_999_999_999  # 十分先の Unix 秒


class TestUniswapV4SwapIntentDecimalCoercion:
    """Decimal 変換・精度テスト。"""

    def test_float_amount_in_converted_to_decimal(self) -> None:
        """float の amount_in が Decimal に変換されること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=1.5,  # type: ignore[arg-type]
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert type(intent.amount_in) is Decimal
        assert intent.amount_in == Decimal("1.5")

    def test_string_amount_in_converted_to_decimal(self) -> None:
        """文字列の amount_in が Decimal に変換されること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in="0.123456789012345678",  # type: ignore[arg-type]
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert type(intent.amount_in) is Decimal
        assert intent.amount_in == Decimal("0.123456789012345678")

    def test_float_slippage_converted_to_decimal(self) -> None:
        """float の slippage が Decimal に変換されること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            slippage=0.01,  # type: ignore[arg-type]
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert type(intent.slippage) is Decimal
        assert intent.slippage == Decimal("0.01")

    def test_float_amount_in_usd_converted_to_decimal(self) -> None:
        """float の amount_in_usd が Decimal に変換されること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
            amount_in_usd=1000.5,  # type: ignore[arg-type]
            portfolio_value_usd=Decimal("20000.0"),
        )
        assert type(intent.amount_in_usd) is Decimal
        assert intent.amount_in_usd == Decimal("1000.5")

    def test_decimal_precision_preserved(self) -> None:
        """Decimal の精度が変換後も保持されること。"""
        precise = Decimal("0.123456789012345678901234567890")
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=precise,
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert intent.amount_in == precise


class TestUniswapV4SwapIntentSlippageBoundary:
    """slippage 境界値テスト。"""

    def test_slippage_default_is_half_percent(self) -> None:
        """slippage デフォルトが 0.005（0.5%）であること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert intent.slippage == Decimal("0.005")

    def test_slippage_min_boundary_rejected(self) -> None:
        """slippage = 0 は gt=0 違反で拒否されること。"""
        with pytest.raises(ValidationError):
            UniswapV4SwapIntent(
                token_in=_TOKEN_IN,
                token_out=_TOKEN_OUT,
                amount_in=Decimal("1.0"),
                slippage=Decimal("0"),
                deadline_unix=_DEADLINE,
                receiver=_RECEIVER,
                chain="ethereum",
            )

    def test_slippage_max_boundary_accepted(self) -> None:
        """slippage = 0.05（5%）は上限境界として許容されること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            slippage=Decimal("0.05"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert intent.slippage == Decimal("0.05")

    def test_slippage_above_max_rejected(self) -> None:
        """slippage > 0.05 は le=0.05 違反で拒否されること。"""
        with pytest.raises(ValidationError):
            UniswapV4SwapIntent(
                token_in=_TOKEN_IN,
                token_out=_TOKEN_OUT,
                amount_in=Decimal("1.0"),
                slippage=Decimal("0.051"),
                deadline_unix=_DEADLINE,
                receiver=_RECEIVER,
                chain="ethereum",
            )

    def test_slippage_small_positive_accepted(self) -> None:
        """slippage = 0.001（0.1%）は許容されること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            slippage=Decimal("0.001"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert intent.slippage == Decimal("0.001")


class TestUniswapV4SwapIntentAmountInValidation:
    """amount_in 検証テスト。"""

    def test_amount_in_zero_rejected(self) -> None:
        """amount_in = 0 は gt=0 違反で拒否されること。"""
        with pytest.raises(ValidationError):
            UniswapV4SwapIntent(
                token_in=_TOKEN_IN,
                token_out=_TOKEN_OUT,
                amount_in=Decimal("0"),
                deadline_unix=_DEADLINE,
                receiver=_RECEIVER,
                chain="ethereum",
            )

    def test_amount_in_negative_rejected(self) -> None:
        """amount_in < 0 は gt=0 違反で拒否されること。"""
        with pytest.raises(ValidationError):
            UniswapV4SwapIntent(
                token_in=_TOKEN_IN,
                token_out=_TOKEN_OUT,
                amount_in=Decimal("-1"),
                deadline_unix=_DEADLINE,
                receiver=_RECEIVER,
                chain="ethereum",
            )

    def test_amount_in_positive_accepted(self) -> None:
        """正の amount_in が受け入れられること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("100"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert intent.amount_in == Decimal("100")


class TestUniswapV4SwapIntentSerialization:
    """JSON シリアライズテスト（Decimal → str）。"""

    def test_amount_in_serialized_as_string(self) -> None:
        """amount_in が JSON で文字列としてシリアライズされること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.5"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        data = intent.model_dump()
        assert isinstance(data["amount_in"], str)
        assert data["amount_in"] == "1.5"

    def test_slippage_serialized_as_string(self) -> None:
        """slippage が JSON で文字列としてシリアライズされること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            slippage=Decimal("0.01"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        data = intent.model_dump()
        assert isinstance(data["slippage"], str)
        assert data["slippage"] == "0.01"

    def test_optional_decimal_none_serialized_as_none(self) -> None:
        """Optional[Decimal] が None の場合は None としてシリアライズされること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        data = intent.model_dump()
        assert data["amount_in_usd"] is None
        assert data["portfolio_value_usd"] is None

    def test_optional_decimal_value_serialized_as_string(self) -> None:
        """Optional[Decimal] が値を持つ場合は文字列としてシリアライズされること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
            amount_in_usd=Decimal("1500.00"),
            portfolio_value_usd=Decimal("20000.00"),
        )
        data = intent.model_dump()
        assert isinstance(data["amount_in_usd"], str)
        assert data["amount_in_usd"] == "1500.00"
        assert isinstance(data["portfolio_value_usd"], str)
        assert data["portfolio_value_usd"] == "20000.00"


class TestUniswapV4SwapIntentDefaults:
    """デフォルト値テスト。"""

    def test_dry_run_default_is_true(self) -> None:
        """dry_run のデフォルトが True であること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_OUT,
            amount_in=Decimal("1.0"),
            deadline_unix=_DEADLINE,
            receiver=_RECEIVER,
            chain="ethereum",
        )
        assert intent.dry_run is True

    def test_chain_invalid_rejected(self) -> None:
        """V4 未デプロイチェーンは Literal 違反で拒否されること。"""
        with pytest.raises(ValidationError):
            UniswapV4SwapIntent(
                token_in=_TOKEN_IN,
                token_out=_TOKEN_OUT,
                amount_in=Decimal("1.0"),
                deadline_unix=_DEADLINE,
                receiver=_RECEIVER,
                chain="bsc",  # type: ignore[arg-type]
            )


class TestUniswapV4SwapEstimate:
    """UniswapV4SwapEstimate テスト。"""

    def test_valid_estimate_creation(self) -> None:
        """is_valid=True の UniswapV4SwapEstimate が生成できること。"""
        estimate = UniswapV4SwapEstimate(
            is_valid=True,
            validation_errors=[],
        )
        assert estimate.is_valid is True
        assert estimate.validation_errors == []
        assert estimate.amount_out_estimate is None

    def test_invalid_estimate_with_errors(self) -> None:
        """is_valid=False の場合に validation_errors が設定されること。"""
        estimate = UniswapV4SwapEstimate(
            is_valid=False,
            validation_errors=["deadline 期限切れ", "token_in == token_out"],
        )
        assert estimate.is_valid is False
        assert len(estimate.validation_errors) == 2

    def test_estimate_decimal_fields_serialized_as_string(self) -> None:
        """Decimal フィールドが文字列としてシリアライズされること。"""
        estimate = UniswapV4SwapEstimate(
            amount_out_estimate=Decimal("1.23"),
            min_amount_out=Decimal("1.20"),
            price_impact_pct=Decimal("0.5"),
            is_valid=True,
        )
        data = estimate.model_dump()
        assert isinstance(data["amount_out_estimate"], str)
        assert isinstance(data["min_amount_out"], str)
        assert isinstance(data["price_impact_pct"], str)
