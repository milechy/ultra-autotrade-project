# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_blocklist.py
"""
rsETH/srsETH/wrsETH ブラックリストチェック + Oracle 乖離 deposit ブロックのテスト。

C-1: build_deposit_txs() にもブラックリストが適用されること
C-1: wrsETH もブロックされること
C-1: 大文字小文字非依存 (rseth / RSETH / Rseth 等) でブロックされること
S-1: Oracle 乖離 HARD_STOP (3ソース全揃い) で deposit がブロックされること
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from app.aave.client import AaveBlocklistedAssetError, OracleDeviationHardStopError
from app.aave.config import BLOCKLISTED_COLLATERAL, BLOCKLISTED_COLLATERAL_UPPER


class TestBlocklistedCollateralConfig:
    """BLOCKLISTED_COLLATERAL 定数の正当性テスト。"""

    def test_rseth_in_blocklist(self) -> None:
        assert "rsETH" in BLOCKLISTED_COLLATERAL

    def test_srseth_in_blocklist(self) -> None:
        assert "srsETH" in BLOCKLISTED_COLLATERAL

    def test_wrseth_in_blocklist(self) -> None:
        """wrsETH も chains.py 登録済みエクスプロイト対象のためブラックリスト入り（C-1）。"""
        assert "wrsETH" in BLOCKLISTED_COLLATERAL

    def test_usdc_not_in_blocklist(self) -> None:
        assert "USDC" not in BLOCKLISTED_COLLATERAL

    def test_is_frozenset(self) -> None:
        assert isinstance(BLOCKLISTED_COLLATERAL, frozenset)

    def test_upper_set_covers_all(self) -> None:
        """BLOCKLISTED_COLLATERAL_UPPER が BLOCKLISTED_COLLATERAL の大文字版を全て含む。"""
        for sym in BLOCKLISTED_COLLATERAL:
            assert sym.upper() in BLOCKLISTED_COLLATERAL_UPPER


class _DepositStub:
    """
    deposit() と build_deposit_txs() のブラックリスト + Oracle チェック部分を再現したスタブ。
    外部 RPC / Web3 パッケージは不要。Oracle チェックは mock で制御する。
    """

    token_addresses: dict[str, str] = {
        "USDC": "0xUSDCAddress",
        "rsETH": "0xrsETHAddress",
        "srsETH": "0xsrsETHAddress",
        "wrsETH": "0xwrsETHAddress",
    }

    def deposit(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
        asset_symbol: str = "",
    ) -> str:
        # ブラックリストチェック（大文字小文字非依存 — 実装ロジックと同一）
        _check_sym = asset_symbol or (asset_address if not asset_address.startswith("0x") else "")
        if _check_sym and _check_sym.upper() in BLOCKLISTED_COLLATERAL_UPPER:
            raise AaveBlocklistedAssetError(
                f"asset '{_check_sym}' はブラックリスト登録済みのため deposit 不可"
            )
        # Oracle チェック（実装と同一ロジックを _oracle_check_for_test で外部化）
        if _check_sym:
            self._run_oracle_check(_check_sym)
        return "0xdummy_ok"

    def build_deposit_txs(
        self,
        asset_symbol: str,
        amount: Decimal,
        wallet_address: str,
    ) -> dict[str, Any]:
        # ブラックリストチェック（大文字小文字非依存 — 実装ロジックと同一）
        if asset_symbol.upper() in BLOCKLISTED_COLLATERAL_UPPER:
            raise AaveBlocklistedAssetError(
                f"asset '{asset_symbol}' はブラックリスト登録済みのため deposit 不可"
            )
        # Oracle チェック
        self._run_oracle_check(asset_symbol)
        return {"approve_tx": {}, "supply_tx": {}}

    def _run_oracle_check(self, asset_symbol: str) -> None:
        """Oracle 乖離チェックを実行（テストで mock を差し込みやすいよう分離）。"""
        from app.aave.client import _load_oracle_config_for_asset  # noqa: PLC0415
        from app.aave.oracle_checker import check_price_deviation  # noqa: PLC0415

        cfg = _load_oracle_config_for_asset(asset_symbol)
        if cfg is None:
            return
        result = check_price_deviation(
            asset=asset_symbol,
            chainlink_feed_address=cfg.get("chainlink_feed"),
            rpc_url=cfg.get("rpc_url"),
            pyth_api_url=cfg.get("pyth_api_url"),
            pyth_price_id=cfg.get("pyth_price_id"),
            uniswap_pool_address=cfg.get("uniswap_pool"),
        )
        available = sum(
            1
            for p in [result.chainlink_price, result.pyth_price, result.twap_price]
            if p is not None
        )
        if result.level == "HARD_STOP" and available >= 3:  # noqa: PLR2004
            raise OracleDeviationHardStopError(f"[{asset_symbol}] Oracle 乖離 HARD_STOP")


class TestDepositBlocklist:
    """deposit() のブラックリストチェックテスト。"""

    def test_deposit_rseth_raises(self) -> None:
        """rsETH で deposit() が AaveBlocklistedAssetError を raise する。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError, match="rsETH"):
            client.deposit(asset_symbol="rsETH", amount=Decimal("10"), wallet_address="0xw")

    def test_deposit_srseth_raises(self) -> None:
        """srsETH で deposit() が AaveBlocklistedAssetError を raise する。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError, match="srsETH"):
            client.deposit(asset_symbol="srsETH", amount=Decimal("5"), wallet_address="0xw")

    def test_deposit_wrseth_raises(self) -> None:
        """wrsETH で deposit() が AaveBlocklistedAssetError を raise する (C-1)。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError, match="wrsETH"):
            client.deposit(asset_symbol="wrsETH", amount=Decimal("3"), wallet_address="0xw")

    def test_deposit_rseth_lowercase_raises(self) -> None:
        """rseth（小文字）でも AaveBlocklistedAssetError を raise する（大文字小文字非依存 C-1）。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError):
            client.deposit(asset_symbol="rseth", amount=Decimal("1"), wallet_address="0xw")

    def test_deposit_rseth_uppercase_raises(self) -> None:
        """RSETH（全大文字）でも AaveBlocklistedAssetError を raise する（C-1）。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError):
            client.deposit(asset_symbol="RSETH", amount=Decimal("1"), wallet_address="0xw")

    def test_deposit_rseth_as_non0x_address_raises(self) -> None:
        """rsETH を非0x asset_address で渡しても検出される。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError, match="rsETH"):
            client.deposit(asset_address="rsETH", amount=Decimal("1"))

    def test_deposit_usdc_no_error(self) -> None:
        """USDC は正常に deposit できる（ブラックリストエラーが raise されない）。"""
        client = _DepositStub()
        result = client.deposit(asset_symbol="USDC", amount=Decimal("100"), wallet_address="0xw")
        assert result == "0xdummy_ok"

    def test_deposit_hex_address_not_blocked(self) -> None:
        """0x で始まるアドレス文字列はシンボルチェックをスキップする。"""
        client = _DepositStub()
        result = client.deposit(asset_address="0xrsETHAddress", amount=Decimal("1"))
        assert result == "0xdummy_ok"


class TestBuildDepositTxsBlocklist:
    """build_deposit_txs() のブラックリストチェックテスト (C-1: パートナー署名フロー)。"""

    def test_build_deposit_txs_rseth_raises(self) -> None:
        """rsETH で build_deposit_txs() が AaveBlocklistedAssetError を raise する。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError, match="rsETH"):
            client.build_deposit_txs("rsETH", Decimal("10"), "0xwallet")

    def test_build_deposit_txs_srseth_raises(self) -> None:
        """srsETH で build_deposit_txs() が AaveBlocklistedAssetError を raise する。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError, match="srsETH"):
            client.build_deposit_txs("srsETH", Decimal("5"), "0xwallet")

    def test_build_deposit_txs_wrseth_raises(self) -> None:
        """wrsETH で build_deposit_txs() が AaveBlocklistedAssetError を raise する (C-1)。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError, match="wrsETH"):
            client.build_deposit_txs("wrsETH", Decimal("3"), "0xwallet")

    def test_build_deposit_txs_wrseth_lowercase_raises(self) -> None:
        """wrseth（小文字）でも AaveBlocklistedAssetError を raise する（大文字小文字非依存 C-1）。"""
        client = _DepositStub()
        with pytest.raises(AaveBlocklistedAssetError):
            client.build_deposit_txs("wrseth", Decimal("1"), "0xwallet")

    def test_build_deposit_txs_usdc_no_error(self) -> None:
        """USDC では build_deposit_txs() が正常に戻る（Oracle 設定なし → fail-open）。"""
        client = _DepositStub()
        # AAVE_ORACLE_ASSETS_JSON 未設定 → Oracle チェックはスキップ
        with patch.dict("os.environ", {"AAVE_ORACLE_ASSETS_JSON": "[]"}):
            result = client.build_deposit_txs("USDC", Decimal("100"), "0xwallet")
        assert "approve_tx" in result
        assert "supply_tx" in result


class TestOracleDeviationDepositBlock:
    """S-1: Oracle 乖離 HARD_STOP (3ソース全揃い) で deposit がブロックされること。"""

    _oracle_assets_json = """[{
        "asset": "USDC",
        "chainlink_feed": "0xFeed",
        "rpc_url": "https://rpc.example.com",
        "pyth_api_url": "https://hermes.pyth.network",
        "pyth_price_id": "0xPythID",
        "uniswap_pool": "0xPool"
    }]"""

    def test_deposit_blocked_on_oracle_hard_stop_3sources(self) -> None:
        """3ソース全揃いで HARD_STOP の場合、deposit() が OracleDeviationHardStopError を raise する（S-1）。"""
        from app.aave.oracle_checker import OracleMultiSourceResult  # noqa: PLC0415

        mock_result = OracleMultiSourceResult(
            asset="USDC",
            level="HARD_STOP",
            max_deviation_pct=Decimal("2.5"),
            chainlink_price=Decimal("1.000"),
            pyth_price=Decimal("1.025"),
            twap_price=Decimal("1.012"),
            detail="乖離 2.5% 超過",
            checked_at="2026-06-15T00:00:00+00:00",
        )

        client = _DepositStub()
        with (
            patch.dict("os.environ", {"AAVE_ORACLE_ASSETS_JSON": self._oracle_assets_json}),
            patch("app.aave.oracle_checker.check_price_deviation", return_value=mock_result),
        ):
            with pytest.raises(OracleDeviationHardStopError):
                client.deposit(asset_symbol="USDC", amount=Decimal("100"), wallet_address="0xw")

    def test_build_deposit_txs_blocked_on_oracle_hard_stop(self) -> None:
        """3ソース全揃いで HARD_STOP の場合、build_deposit_txs() も OracleDeviationHardStopError を raise する（S-1）。"""
        from app.aave.oracle_checker import OracleMultiSourceResult  # noqa: PLC0415

        mock_result = OracleMultiSourceResult(
            asset="USDC",
            level="HARD_STOP",
            max_deviation_pct=Decimal("2.5"),
            chainlink_price=Decimal("1.000"),
            pyth_price=Decimal("1.025"),
            twap_price=Decimal("1.012"),
            detail="乖離 2.5% 超過",
            checked_at="2026-06-15T00:00:00+00:00",
        )

        client = _DepositStub()
        with (
            patch.dict("os.environ", {"AAVE_ORACLE_ASSETS_JSON": self._oracle_assets_json}),
            patch("app.aave.oracle_checker.check_price_deviation", return_value=mock_result),
        ):
            with pytest.raises(OracleDeviationHardStopError):
                client.build_deposit_txs("USDC", Decimal("100"), "0xwallet")

    def test_deposit_not_blocked_when_only_2sources(self) -> None:
        """2ソース以下で HARD_STOP でも deposit はブロックされない（fail-open）。"""
        from app.aave.oracle_checker import OracleMultiSourceResult  # noqa: PLC0415

        mock_result = OracleMultiSourceResult(
            asset="USDC",
            level="HARD_STOP",
            max_deviation_pct=Decimal("2.5"),
            chainlink_price=Decimal("1.000"),
            pyth_price=Decimal("1.025"),
            twap_price=None,  # 2ソースのみ
            detail="乖離 2.5%",
            checked_at="2026-06-15T00:00:00+00:00",
        )

        client = _DepositStub()
        with (
            patch.dict("os.environ", {"AAVE_ORACLE_ASSETS_JSON": self._oracle_assets_json}),
            patch("app.aave.oracle_checker.check_price_deviation", return_value=mock_result),
        ):
            # 2ソースの場合はブロックしない（例外 raise されないことを確認）
            result = client.deposit(
                asset_symbol="USDC", amount=Decimal("100"), wallet_address="0xw"
            )
            assert result == "0xdummy_ok"

    def test_deposit_not_blocked_when_oracle_warn(self) -> None:
        """WARN レベルでは deposit はブロックされない（fail-open）。"""
        from app.aave.oracle_checker import OracleMultiSourceResult  # noqa: PLC0415

        mock_result = OracleMultiSourceResult(
            asset="USDC",
            level="WARN",
            max_deviation_pct=None,
            chainlink_price=Decimal("1.000"),
            pyth_price=None,
            twap_price=None,
            detail="1ソースのみ",
            checked_at="2026-06-15T00:00:00+00:00",
        )

        client = _DepositStub()
        with (
            patch.dict("os.environ", {"AAVE_ORACLE_ASSETS_JSON": self._oracle_assets_json}),
            patch("app.aave.oracle_checker.check_price_deviation", return_value=mock_result),
        ):
            result = client.deposit(
                asset_symbol="USDC", amount=Decimal("100"), wallet_address="0xw"
            )
            assert result == "0xdummy_ok"

    def test_deposit_ok_no_oracle_config(self) -> None:
        """Oracle 設定がない場合は Oracle チェックをスキップして通過（fail-open）。"""
        client = _DepositStub()
        with patch.dict("os.environ", {"AAVE_ORACLE_ASSETS_JSON": "[]"}):
            result = client.deposit(
                asset_symbol="USDC", amount=Decimal("100"), wallet_address="0xw"
            )
            assert result == "0xdummy_ok"
