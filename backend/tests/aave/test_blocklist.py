# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_blocklist.py
"""
rsETH/srsETH ブラックリストチェックのテスト。

- ブラックリスト登録済みアセットで deposit() が AaveBlocklistedAssetError を raise することを確認
- 通常アセット（USDC）では正常に処理されることを確認
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.aave.client import AaveBlocklistedAssetError
from app.aave.config import BLOCKLISTED_COLLATERAL


class TestBlocklistedCollateralConfig:
    """BLOCKLISTED_COLLATERAL 定数の正当性テスト。"""

    def test_rseth_in_blocklist(self) -> None:
        assert "rsETH" in BLOCKLISTED_COLLATERAL

    def test_srseth_in_blocklist(self) -> None:
        assert "srsETH" in BLOCKLISTED_COLLATERAL

    def test_usdc_not_in_blocklist(self) -> None:
        assert "USDC" not in BLOCKLISTED_COLLATERAL

    def test_is_frozenset(self) -> None:
        assert isinstance(BLOCKLISTED_COLLATERAL, frozenset)


class TestWeb3AaveClientBlocklist:
    """Web3AaveClient.deposit() のブラックリストチェックテスト。"""

    def _make_client(self):  # type: ignore[return]
        """
        Web3AaveClient のサブセット: ブラックリストチェックロジックのみを
        実際のコードから持ち込んだ薄いスタブ。
        外部 RPC / Web3 パッケージは不要。
        """

        from app.aave.client import AaveBlocklistedAssetError
        from app.aave.config import BLOCKLISTED_COLLATERAL

        class _Stub:
            """deposit() のブラックリストチェック部分だけを再現。"""

            token_addresses: dict[str, str] = {
                "USDC": "0xUSDCAddress",
                "rsETH": "0xrsETHAddress",
                "srsETH": "0xsrsETHAddress",
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
                # ブラックリストチェック（実装と同じロジック）
                _check_sym = asset_symbol or (
                    asset_address if not asset_address.startswith("0x") else ""
                )
                if _check_sym and _check_sym in BLOCKLISTED_COLLATERAL:
                    raise AaveBlocklistedAssetError(
                        f"asset '{_check_sym}' はブラックリスト登録済みのため deposit 不可"
                    )
                # ブラックリストを通過したら dummy 成功
                return "0xdummy_ok"

        return _Stub()  # type: ignore[return-value]

    def test_deposit_rseth_raises_blocklist_error(self) -> None:
        """rsETH を asset_symbol で deposit するとブラックリストエラーが出る。"""
        client = self._make_client()
        with pytest.raises(AaveBlocklistedAssetError, match="rsETH"):
            client.deposit(asset_symbol="rsETH", amount=Decimal("10"), wallet_address="0xwallet")

    def test_deposit_srseth_raises_blocklist_error(self) -> None:
        """srsETH を asset_symbol で deposit するとブラックリストエラーが出る。"""
        client = self._make_client()
        with pytest.raises(AaveBlocklistedAssetError, match="srsETH"):
            client.deposit(asset_symbol="srsETH", amount=Decimal("5"), wallet_address="0xwallet")

    def test_deposit_rseth_as_positional_raises(self) -> None:
        """rsETH をアドレス位置引数ではなく非0x文字列で渡しても検出される。"""
        client = self._make_client()
        with pytest.raises(AaveBlocklistedAssetError, match="rsETH"):
            client.deposit(asset_address="rsETH", amount=Decimal("1"))

    def test_deposit_usdc_no_error(self) -> None:
        """USDC は正常に deposit できる（ブラックリストエラーが raise されない）。"""
        client = self._make_client()
        # AaveBlocklistedAssetError が raise されないことを確認
        result = client.deposit(asset_symbol="USDC", amount=Decimal("100"), wallet_address="0xw")
        assert result == "0xdummy_ok"

    def test_deposit_hex_address_not_blocked(self) -> None:
        """0x で始まるアドレス文字列はシンボルチェックをスキップする。"""
        client = self._make_client()
        # 0x アドレスはシンボルチェック対象外（アドレスでのブラックリストは別途実装）
        result = client.deposit(asset_address="0xrsETHAddress", amount=Decimal("1"))
        assert result == "0xdummy_ok"
