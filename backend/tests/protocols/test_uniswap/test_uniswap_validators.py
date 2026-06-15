# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Uniswap V4 バリデータのユニットテスト。"""

from decimal import Decimal

import pytest

from app.protocols.uniswap.schemas import UniswapV4SwapIntent
from app.protocols.uniswap.validators import compute_min_amount_out, validate_swap_intent

# テスト用の固定値
_TOKEN_IN = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"  # USDC (Ethereum mainnet)
_TOKEN_OUT = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # WETH (Ethereum mainnet)
_RECEIVER = "0x" + "a" * 40
_NOW_UNIX = 1_718_000_000  # 固定基準時刻（テスト注入用）
_FUTURE_DEADLINE = _NOW_UNIX + 3600  # 1時間後


def _make_intent(**kwargs: object) -> UniswapV4SwapIntent:
    """テスト用デフォルト UniswapV4SwapIntent を生成する。"""
    defaults: dict[str, object] = {
        "token_in": _TOKEN_IN,
        "token_out": _TOKEN_OUT,
        "amount_in": Decimal("1.0"),
        "deadline_unix": _FUTURE_DEADLINE,
        "receiver": _RECEIVER,
        "chain": "ethereum",
    }
    defaults.update(kwargs)
    return UniswapV4SwapIntent(**defaults)  # type: ignore[arg-type]


class TestValidateSwapIntentDeadline:
    """deadline_unix チェックテスト。"""

    def test_expired_deadline_rejected(self) -> None:
        """deadline_unix <= now_unix の場合は拒否されること。"""
        intent = _make_intent(deadline_unix=_NOW_UNIX)  # now と同値
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False
        assert any("deadline" in e for e in result.validation_errors)

    def test_past_deadline_rejected(self) -> None:
        """deadline_unix が過去の場合は拒否されること。"""
        intent = _make_intent(deadline_unix=_NOW_UNIX - 1)
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False

    def test_future_deadline_accepted(self) -> None:
        """deadline_unix が未来の場合は通過すること。"""
        intent = _make_intent(deadline_unix=_NOW_UNIX + 1)
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True
        assert result.validation_errors == []

    def test_far_future_deadline_accepted(self) -> None:
        """十分先の deadline_unix が通過すること。"""
        intent = _make_intent(deadline_unix=_NOW_UNIX + 86400)  # 24時間後
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True


class TestValidateSwapIntentTokenPair:
    """token_in / token_out チェックテスト。"""

    def test_same_token_rejected(self) -> None:
        """token_in == token_out の場合は拒否されること。"""
        intent = _make_intent(token_in=_TOKEN_IN, token_out=_TOKEN_IN)
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False
        assert any("token_in" in e and "token_out" in e for e in result.validation_errors)

    def test_same_token_case_insensitive_rejected(self) -> None:
        """大文字小文字が異なる場合も同一トークンとして拒否されること。"""
        intent = _make_intent(
            token_in=_TOKEN_IN.lower(),
            token_out=_TOKEN_IN.upper(),
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False

    def test_different_tokens_accepted(self) -> None:
        """異なるトークンペアは通過すること。"""
        intent = _make_intent(token_in=_TOKEN_IN, token_out=_TOKEN_OUT)
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True


class TestValidateSwapIntentReceiver:
    """receiver チェックテスト。"""

    def test_empty_receiver_rejected(self) -> None:
        """receiver が空文字の場合は拒否されること。"""
        intent = _make_intent(receiver="")
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False
        assert any("receiver" in e for e in result.validation_errors)

    def test_whitespace_only_receiver_rejected(self) -> None:
        """receiver が空白のみの場合は拒否されること。"""
        intent = _make_intent(receiver="   ")
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False

    def test_valid_receiver_accepted(self) -> None:
        """有効な receiver アドレスが通過すること。"""
        intent = _make_intent(receiver=_RECEIVER)
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True


class TestValidateSwapIntentPortfolioLimit:
    """単一取引10%上限チェックテスト（Security Rules §3）。"""

    def test_within_10_percent_accepted(self) -> None:
        """amount_in_usd が portfolio の 10% 以内は通過すること。"""
        intent = _make_intent(
            portfolio_value_usd=Decimal("10000"),
            amount_in_usd=Decimal("1000"),  # ちょうど10%
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True

    def test_exceeding_10_percent_rejected(self) -> None:
        """amount_in_usd が portfolio の 10% を超える場合は拒否されること。"""
        intent = _make_intent(
            portfolio_value_usd=Decimal("10000"),
            amount_in_usd=Decimal("1001"),  # 10.01%
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False
        assert any("10%" in e or "上限" in e for e in result.validation_errors)

    def test_far_exceeding_10_percent_rejected(self) -> None:
        """amount_in_usd が portfolio の 50% の場合も拒否されること。"""
        intent = _make_intent(
            portfolio_value_usd=Decimal("10000"),
            amount_in_usd=Decimal("5000"),
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False

    def test_amount_in_usd_only_fail_closed(self) -> None:
        """amount_in_usd のみ指定（portfolio_value_usd 未指定）は fail-closed 拒否。"""
        intent = _make_intent(
            amount_in_usd=Decimal("100"),
            portfolio_value_usd=None,
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False
        assert any("fail-closed" in e or "片方のみ" in e for e in result.validation_errors)

    def test_portfolio_value_only_fail_closed(self) -> None:
        """portfolio_value_usd のみ指定（amount_in_usd 未指定）は fail-closed 拒否。"""
        intent = _make_intent(
            amount_in_usd=None,
            portfolio_value_usd=Decimal("10000"),
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False
        assert any("fail-closed" in e or "片方のみ" in e for e in result.validation_errors)

    def test_both_none_skips_check(self) -> None:
        """両方 None の場合は10%チェックをスキップして通過すること。"""
        intent = _make_intent(
            amount_in_usd=None,
            portfolio_value_usd=None,
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True

    def test_zero_portfolio_skips_comparison(self) -> None:
        """portfolio_value_usd = 0 の場合は比較をスキップして通過すること（ゼロ除算防止）。"""
        intent = _make_intent(
            portfolio_value_usd=Decimal("0"),
            amount_in_usd=Decimal("0"),
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True


class TestComputeMinAmountOut:
    """compute_min_amount_out のテスト。"""

    def test_basic_calculation(self) -> None:
        """基本的な計算が正しいこと。"""
        result = compute_min_amount_out(
            amount_out_estimate=Decimal("1.0"),
            slippage=Decimal("0.005"),
        )
        assert result == Decimal("0.995")

    def test_decimal_precision(self) -> None:
        """Decimal 精度が保持されること（float 精度劣化なし）。"""
        result = compute_min_amount_out(
            amount_out_estimate=Decimal("3.141592653589793238"),
            slippage=Decimal("0.005"),
        )
        expected = Decimal("3.141592653589793238") * (Decimal("1") - Decimal("0.005"))
        assert result == expected

    def test_result_type_is_decimal(self) -> None:
        """結果が Decimal 型であること（float 返却禁止）。"""
        result = compute_min_amount_out(
            amount_out_estimate=Decimal("100"),
            slippage=Decimal("0.01"),
        )
        assert type(result) is Decimal

    def test_max_slippage_boundary(self) -> None:
        """slippage = 0.05（5%）の境界値計算。"""
        result = compute_min_amount_out(
            amount_out_estimate=Decimal("100"),
            slippage=Decimal("0.05"),
        )
        assert result == Decimal("95")

    def test_small_slippage(self) -> None:
        """slippage = 0.001（0.1%）の計算。"""
        result = compute_min_amount_out(
            amount_out_estimate=Decimal("1000"),
            slippage=Decimal("0.001"),
        )
        assert result == Decimal("999")

    def test_large_amount_precision(self) -> None:
        """大きな amount での精度保持。"""
        result = compute_min_amount_out(
            amount_out_estimate=Decimal("1000000.000000000000000001"),
            slippage=Decimal("0.005"),
        )
        expected = Decimal("1000000.000000000000000001") * Decimal("0.995")
        assert result == expected


class TestStablecoinDetectionReuse:
    """SlippageGuard.is_stablecoin 再利用テスト。"""

    def test_stablecoin_pair_passes_validation(self) -> None:
        """ステーブルコインシンボル同士のスワップはバリデーション自体を通過すること。

        Phase 1 では reject しない（補足情報の記録のみ）。
        token はシンボル文字列（"USDC" 等）で指定してテスト。
        """
        intent = UniswapV4SwapIntent(
            token_in="USDC",
            token_out="USDT",
            amount_in=Decimal("1000"),
            deadline_unix=_FUTURE_DEADLINE,
            receiver=_RECEIVER,
            chain="base",
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        # Phase 1: ステーブルコイン同士でも reject しない
        assert result.is_valid is True

    def test_non_stablecoin_accepted(self) -> None:
        """非ステーブルコインのアドレス形式は is_stablecoin=False となり通常通過すること。"""
        intent = _make_intent(token_in=_TOKEN_IN, token_out=_TOKEN_OUT)
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is True


class TestMultipleErrorAccumulation:
    """複数エラー同時検出テスト。"""

    def test_multiple_errors_accumulated(self) -> None:
        """複数の問題が同時に存在する場合、全エラーが収集されること。"""
        intent = UniswapV4SwapIntent(
            token_in=_TOKEN_IN,
            token_out=_TOKEN_IN,  # 同一トークン
            amount_in=Decimal("1.0"),
            deadline_unix=_NOW_UNIX,  # 期限切れ
            receiver="",  # 空 receiver
            chain="ethereum",
        )
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.is_valid is False
        # deadline + token_in==token_out + receiver の3エラーを期待
        assert len(result.validation_errors) >= 2

    def test_estimate_fields_are_none_in_phase1(self) -> None:
        """Phase 1 では amount_out_estimate / min_amount_out が None であること。"""
        intent = _make_intent()
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert result.amount_out_estimate is None
        assert result.min_amount_out is None
        assert result.price_impact_pct is None


class TestReturnType:
    """戻り値型テスト。"""

    def test_returns_estimate_instance(self) -> None:
        """validate_swap_intent が UniswapV4SwapEstimate を返すこと。"""
        from app.protocols.uniswap.schemas import UniswapV4SwapEstimate

        intent = _make_intent()
        result = validate_swap_intent(intent, now_unix=_NOW_UNIX)
        assert isinstance(result, UniswapV4SwapEstimate)

    @pytest.mark.parametrize(
        "slippage,amount",
        [
            (Decimal("0.001"), Decimal("100")),
            (Decimal("0.005"), Decimal("1000")),
            (Decimal("0.05"), Decimal("999")),
        ],
    )
    def test_compute_min_amount_out_parametrized(self, slippage: Decimal, amount: Decimal) -> None:
        """parametrize で複数スリッページ/量を確認。"""
        result = compute_min_amount_out(amount, slippage)
        expected = amount * (Decimal("1") - slippage)
        assert result == expected
        assert type(result) is Decimal
