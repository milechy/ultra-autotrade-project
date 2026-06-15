# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_oracle_checker.py
"""
多重 Oracle 価格乖離チェック (check_price_deviation) のテスト。

- 乖離率1% → level="OK"
- 乖離率2.5% → level="HARD_STOP"
- Pyth API 失敗時は fail-open（Chainlink + TWAP の2価格で継続）
- 外部 RPC / API はすべて mock する（実ネットワーク呼び出しなし）

金融計算は全て Decimal — float 禁止の確認も含む。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from unittest.mock import patch

import pytest

from app.aave.oracle_checker import (
    OracleMultiSourceResult,
    _max_deviation_pct,
    check_price_deviation,
)


class TestMaxDeviationPct:
    """_max_deviation_pct() の単体テスト。"""

    def test_two_prices_no_deviation(self) -> None:
        result = _max_deviation_pct([Decimal("1.00"), Decimal("1.00")])
        assert result == Decimal("0")

    def test_two_prices_1pct(self) -> None:
        result = _max_deviation_pct([Decimal("1.00"), Decimal("1.01")])
        # 1.01 / 1.00 - 1 = 1%
        assert result == pytest.approx(Decimal("1.0"), rel=Decimal("0.001"))

    def test_three_prices_2_5pct(self) -> None:
        # min=1.00, max=1.025 → 2.5%
        result = _max_deviation_pct([Decimal("1.00"), Decimal("1.010"), Decimal("1.025")])
        assert result == pytest.approx(Decimal("2.5"), rel=Decimal("0.001"))

    def test_single_price_returns_zero(self) -> None:
        result = _max_deviation_pct([Decimal("1.00")])
        assert result == Decimal("0")

    def test_empty_list_returns_zero(self) -> None:
        result = _max_deviation_pct([])
        assert result == Decimal("0")

    def test_result_is_decimal(self) -> None:
        """戻り値が Decimal であること（float 混入チェック）。"""
        result = _max_deviation_pct([Decimal("1.00"), Decimal("1.01")])
        assert isinstance(result, Decimal)


class TestCheckPriceDeviation:
    """check_price_deviation() のテスト。外部 RPC/API はすべて mock する。"""

    def _patch_all(
        self,
        chainlink_price: Optional[Decimal],
        pyth_price: Optional[Decimal],
        twap_price: Optional[Decimal],
    ):
        """3つの価格取得関数を一括 patch してコンテキストマネージャを返す。"""
        import contextlib  # noqa: PLC0415

        @contextlib.contextmanager
        def _ctx():
            with (
                patch(
                    "app.aave.oracle_checker._get_chainlink_price",
                    return_value=chainlink_price,
                ),
                patch(
                    "app.aave.oracle_checker._get_pyth_price",
                    return_value=pyth_price,
                ),
                patch(
                    "app.aave.oracle_checker._get_uniswap_v3_twap",
                    return_value=twap_price,
                ),
            ):
                yield

        return _ctx()

    def test_ok_when_deviation_below_threshold(self) -> None:
        """3価格の乖離率 < 2% → level="OK"。"""
        # Chainlink=1.000, Pyth=1.005, TWAP=1.008 → max_dev ≈ 0.8%
        with self._patch_all(Decimal("1.000"), Decimal("1.005"), Decimal("1.008")):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
                pyth_api_url="https://hermes.pyth.network",
                pyth_price_id="0xPythID",
                uniswap_pool_address="0xPool",
            )

        assert result.level == "OK"
        assert result.max_deviation_pct is not None
        assert result.max_deviation_pct < Decimal("2")
        assert isinstance(result.max_deviation_pct, Decimal)

    def test_hard_stop_when_deviation_exceeds_threshold(self) -> None:
        """乖離率 2.5% → level="HARD_STOP"。"""
        # Chainlink=1.000, Pyth=1.025 → 2.5%
        with self._patch_all(Decimal("1.000"), Decimal("1.025"), Decimal("1.012")):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
                pyth_api_url="https://hermes.pyth.network",
                pyth_price_id="0xPythID",
                uniswap_pool_address="0xPool",
            )

        assert result.level == "HARD_STOP"
        assert result.max_deviation_pct is not None
        assert result.max_deviation_pct >= Decimal("2")

    def test_exactly_at_threshold_is_hard_stop(self) -> None:
        """乖離率がちょうど 2% でも HARD_STOP。"""
        # Chainlink=1.000, Pyth=1.020 → 2.0% exactly
        with self._patch_all(Decimal("1.000"), Decimal("1.020"), None):
            result = check_price_deviation(
                asset="WETH",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
                pyth_api_url="https://hermes.pyth.network",
                pyth_price_id="0xPythID",
            )

        assert result.level == "HARD_STOP"

    def test_pyth_failure_fail_open(self) -> None:
        """Pyth API 失敗（None）時は Chainlink + TWAP の2価格で継続 (fail-open)。"""
        # Pyth = None (取得失敗), Chainlink=1.000, TWAP=1.005 → 0.5% → OK
        with self._patch_all(Decimal("1.000"), None, Decimal("1.005")):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
                pyth_api_url="https://hermes.pyth.network",
                pyth_price_id="0xPythID",
                uniswap_pool_address="0xPool",
            )

        # Pyth 失敗でも2価格あれば level="OK" (乖離 < 2%)
        assert result.level == "OK"
        assert result.pyth_price is None
        assert result.chainlink_price == Decimal("1.000")
        assert result.twap_price == Decimal("1.005")

    def test_all_sources_fail_returns_warn(self) -> None:
        """全ソース取得失敗時は level="WARN" (2価格未満)。"""
        with self._patch_all(None, None, None):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
            )

        assert result.level == "WARN"
        assert result.max_deviation_pct is None

    def test_only_one_source_returns_warn(self) -> None:
        """1価格のみ → level="WARN"。"""
        with self._patch_all(Decimal("1.000"), None, None):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
            )

        assert result.level == "WARN"

    def test_returns_oracle_multi_source_result(self) -> None:
        """戻り値が OracleMultiSourceResult インスタンスであること。"""
        with self._patch_all(Decimal("1.000"), Decimal("1.001"), Decimal("1.002")):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
            )

        assert isinstance(result, OracleMultiSourceResult)

    def test_asset_name_in_result(self) -> None:
        """asset 名が結果に反映される。"""
        with self._patch_all(Decimal("1.000"), Decimal("1.001"), None):
            result = check_price_deviation(
                asset="MyToken",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
            )

        assert result.asset == "MyToken"

    def test_custom_deviation_threshold(self) -> None:
        """カスタム閾値 5% で 2.5% 乖離は OK になる。"""
        # pyth_api_url/uniswap_pool_address も渡して mock が全ソースに効くようにする
        with self._patch_all(Decimal("1.000"), Decimal("1.025"), Decimal("1.012")):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
                pyth_api_url="https://hermes.pyth.network",
                pyth_price_id="0xPythID",
                uniswap_pool_address="0xPool",
                deviation_threshold_pct=Decimal("5"),
            )

        assert result.level == "OK"

    def test_prices_are_decimal_in_result(self) -> None:
        """結果の price フィールドが Decimal 型であること（float 混入なし）。"""
        with self._patch_all(Decimal("1.000"), Decimal("1.001"), Decimal("1.002")):
            result = check_price_deviation(
                asset="USDC",
                chainlink_feed_address="0xFeed",
                rpc_url="https://rpc.example.com",
                pyth_api_url="https://hermes.pyth.network",
                pyth_price_id="0xID",
                uniswap_pool_address="0xPool",
            )

        assert isinstance(result.chainlink_price, Decimal)
        assert isinstance(result.pyth_price, Decimal)
        assert isinstance(result.twap_price, Decimal)
        assert isinstance(result.max_deviation_pct, Decimal)
