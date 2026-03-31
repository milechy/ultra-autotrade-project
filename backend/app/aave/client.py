# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/client.py
"""
Aave V3 クライアント — web3.py ベース。

CLAUDE.md: Start Small, Iterate
Step 1: get_health_factor() のみ実装。
Step 2: deposit() + テスト（次イテレーション）
Step 3: withdraw() + 統合テスト（その次）

セキュリティ: docs/13_security_design.md
- 秘密鍵は環境変数のみ（ハードコード禁止）
- ログにアドレス・キーを出さない
- 金額計算は Decimal のみ（float 禁止）
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Protocol

from .config import AaveSettings, get_aave_settings
from .gas_estimator import (
    DEFAULT_FALLBACK_GAS_APPROVE,
    DEFAULT_FALLBACK_GAS_SUPPLY,
    DEFAULT_FALLBACK_GAS_WITHDRAW,
    GasEstimator,
)

logger = logging.getLogger(__name__)

# web3 はオプション依存。モジュールレベルで参照を試み、未インストール時は None にする。
# これにより @patch("app.aave.client.Web3") が正常に機能する。
try:
    from web3 import Web3
except ImportError:
    Web3 = None  # type: ignore[assignment,misc]

# Aave V3 Pool ABI（getUserAccountData + supply — 最小限）
_POOL_ABI_MINIMAL = [
    {
        "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
        "name": "getUserAccountData",
        "outputs": [
            {"internalType": "uint256", "name": "totalCollateralBase", "type": "uint256"},
            {"internalType": "uint256", "name": "totalDebtBase", "type": "uint256"},
            {"internalType": "uint256", "name": "availableBorrowsBase", "type": "uint256"},
            {"internalType": "uint256", "name": "currentLiquidationThreshold", "type": "uint256"},
            {"internalType": "uint256", "name": "ltv", "type": "uint256"},
            {"internalType": "uint256", "name": "healthFactor", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
        ],
        "name": "supply",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"},
        ],
        "name": "withdraw",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ERC-20 ABI（approve + decimals — 最小限）
_ERC20_ABI_MINIMAL = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Aave V3 Pool アドレス（Sepolia テストネット）
# 出典: https://docs.aave.com/developers/deployed-contracts/v3-testnet-addresses
_POOL_ADDRESS_SEPOLIA = "0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951"

# Sepolia USDC アドレス
_USDC_ADDRESS_SEPOLIA = "0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8"

# Aave V3 Pool アドレス（Arbitrum Mainnet）
_POOL_ADDRESS_ARBITRUM = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"

# Arbitrum USDC.e アドレス
_USDC_ADDRESS_ARBITRUM = "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"

# Aave V3 Pool アドレス（Arbitrum Sepolia）
_POOL_ADDRESS_ARBITRUM_SEPOLIA = "0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff"

# Arbitrum Sepolia USDC
_USDC_ADDRESS_ARBITRUM_SEPOLIA = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"


@dataclass
class AccountData:
    """Aave V3 account data from getUserAccountData()."""

    total_collateral_usd: Decimal
    total_debt_usd: Decimal
    available_borrows_usd: Decimal
    health_factor: Decimal


class AaveClientBase(ABC):
    """Aave クライアントの抽象基底クラス。"""

    @abstractmethod
    def get_health_factor(self, wallet_address: str) -> Decimal:
        """
        ウォレットの現在の Health Factor を取得する。

        Returns:
            Decimal: Health Factor 値。
                     ポジションなし（担保なし）の場合は Decimal("inf") を返す。
        Raises:
            AaveClientError: RPC 接続失敗・コントラクト呼び出し失敗時。
        """

    @abstractmethod
    def deposit(
        self,
        asset_address: str,
        amount: Decimal,
        wallet_address: str,
        private_key: str,
        dry_run: bool = False,
    ) -> "dict[str, Any] | str":
        """
        Aave V3 Pool に deposit（supply）する。

        Args:
            asset_address: ERC-20 トークンのアドレス
            amount: deposit する量（人間が読める単位、例: 10.5 USDC）
            wallet_address: 送信元ウォレットアドレス
            private_key: 秘密鍵（tx署名用）
            dry_run: True の場合は tx を送信しない

        Returns:
            dict: {"tx_hash": "0x...", "amount": "...", "dry_run": bool}
            str: 後方互換（asset_symbol 呼び出し時）

        Raises:
            AaveClientError: トランザクション失敗時
            ValueError: amount <= 0 の場合
        """

    @abstractmethod
    def withdraw(
        self,
        asset_address: str,
        amount: Decimal,
        wallet_address: str,
        private_key: str,
        dry_run: bool = False,
    ) -> "dict[str, Any] | str":
        """
        Aave V3 Pool から withdraw する。

        HF < 1.6 の場合は AaveClientError を raise する（docs/13 rule 2）。
        """

    @abstractmethod
    def get_account_data(self, wallet_address: str) -> AccountData: ...


class AaveClientError(Exception):
    """Aave クライアントの基底例外。"""


# 後方互換: 旧コードが AaveTransactionError を参照している箇所のため維持
class AaveTransactionError(AaveClientError):
    """トランザクション送信・実行エラー。"""


# 後方互換: service.py が AaveClient Protocol を使っているため維持
class AaveClient(Protocol):
    """
    Aave クライアントのインターフェース（後方互換 Protocol）。

    deposit / withdraw / get_health_factor を備えた実装であれば差し替え可能。
    """

    def get_health_factor(self) -> Optional[Decimal]:
        """現在のポジションのヘルスファクターを返す。"""

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        """指定したトークンを Aave に deposit する。"""

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        """指定したトークンを Aave から withdraw する。"""

    def get_account_data(self, wallet_address: str) -> "AccountData":
        """Aave V3 Pool のアカウントデータを取得する。"""


class DummyAaveClient(AaveClientBase):
    """
    テスト・ローカル開発用のダミークライアント。

    AAVE_CLIENT_TYPE=dummy の場合に使用。
    実際の RPC 接続は行わない。

    後方互換のため settings 引数を受け付けるが、無視する。
    """

    def __init__(self, settings: Optional[AaveSettings] = None) -> None:
        # settings は後方互換のために受け付けるが、ダミークライアントでは使用しない
        _ = settings

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        logger.info("DummyAaveClient.get_health_factor called (no RPC)")
        return Decimal("2.5")  # 安全な値を返す

    def get_account_data(self, wallet_address: str) -> AccountData:
        return AccountData(
            total_collateral_usd=Decimal("10000"),
            total_debt_usd=Decimal("3000"),
            available_borrows_usd=Decimal("5000"),
            health_factor=Decimal("2.5"),
        )

    def deposit(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
        # 後方互換: 旧コードは deposit(asset_symbol, amount) と呼び出す
        asset_symbol: str = "",
    ) -> "dict[str, Any] | str":
        logger.info("DummyAaveClient.deposit called (no tx sent)")
        # 後方互換: asset_symbol が渡された場合は文字列を返す
        if asset_symbol:
            return f"dummy-deposit-{asset_symbol}-{amount}"
        # asset_address が最初の位置引数として asset_symbol 扱いで渡された場合も検出
        # service.py は deposit(token, amount) と呼び出すため
        if asset_address and not asset_address.startswith("0x"):
            return f"dummy-deposit-{asset_address}-{amount}"
        return {
            "tx_hash": "0xdummy_deposit_hash",
            "amount": str(amount),
            "dry_run": dry_run,
        }

    def withdraw(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
        asset_symbol: str = "",
    ) -> "dict[str, Any] | str":
        logger.info("DummyAaveClient.withdraw called (no tx sent)")
        # backward compat: old service.py calls withdraw(asset_symbol, amount) → str
        if asset_symbol:
            return f"dummy-withdraw-{asset_symbol}-{amount}"
        if asset_address and not asset_address.startswith("0x"):
            return f"dummy-withdraw-{asset_address}-{amount}"
        return {
            "tx_hash": "0xdummy_withdraw_hash",
            "amount": str(amount),
            "dry_run": dry_run,
        }


class Web3AaveClient(AaveClientBase):
    """
    web3.py を使った Aave V3 本実装クライアント。

    AAVE_CLIENT_TYPE=web3 の場合に使用。
    現時点では get_health_factor() のみ実装。

    後方互換のため settings 引数も受け付ける。
    web3 は遅延インポート（テスト時にモックしやすくするため）。
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        pool_address: str = _POOL_ADDRESS_SEPOLIA,
        settings: Optional[AaveSettings] = None,
        flashbots_rpc_url: Optional[str] = None,
    ) -> None:
        # web3 はモジュールレベルで参照（テスト時にモックしやすくするため）
        if Web3 is None:
            raise AaveClientError("web3 package is required. Install with: pip install web3")

        # 後方互換: settings から rpc_url/pool_address を取得することもできる
        if settings is not None:
            if not settings.rpc_url:
                raise AaveClientError("AAVE_RPC_URL is required for Web3AaveClient")
            if not settings.wallet_private_key:
                raise AaveClientError("AAVE_WALLET_PRIVATE_KEY is required for Web3AaveClient")
            if not settings.pool_address:
                raise AaveClientError("AAVE_POOL_ADDRESS is required for Web3AaveClient")
            if not settings.usdc_address:
                raise AaveClientError("AAVE_USDC_ADDRESS is required for Web3AaveClient")
            effective_rpc_url = settings.rpc_url
            effective_pool_address = settings.pool_address
        else:
            if not rpc_url:
                raise AaveClientError("AAVE_RPC_URL is required for Web3AaveClient")
            effective_rpc_url = rpc_url
            effective_pool_address = pool_address

        # RPCProvider でフェイルオーバーを有効化
        _secondary_url: Optional[str] = None
        if settings is not None:
            _secondary_url = getattr(settings, "rpc_url_secondary", None)
        from .rpc_provider import RPCProvider  # noqa: PLC0415

        self._rpc_provider = RPCProvider(effective_rpc_url, _secondary_url, web3_cls=Web3)
        try:
            self._w3 = self._rpc_provider.get_web3()
        except ConnectionError as exc:
            raise AaveClientError(
                f"RPC に接続できません: {effective_rpc_url[:20]}..."
            ) from exc  # URLを切り詰めてログ
        if not self._w3.is_connected():
            raise AaveClientError(
                f"RPC に接続できません: {effective_rpc_url[:20]}..."
            )  # URLを切り詰めてログ
        self._pool = self._w3.eth.contract(
            address=Web3.to_checksum_address(effective_pool_address),
            abi=_POOL_ABI_MINIMAL,
        )

        # Flashbots Protect RPC（MEV対策）
        _fb_url: Optional[str] = None
        if settings is not None:
            _fb_url = getattr(settings, "flashbots_rpc_url", None)
        if flashbots_rpc_url is not None:
            _fb_url = flashbots_rpc_url
        if _fb_url:
            self._w3_tx = Web3(Web3.HTTPProvider(_fb_url))
            logger.info("Flashbots Protect RPC 設定完了 (endpoint=%s...)", _fb_url[:30])
        else:
            self._w3_tx = self._w3

        # 後方互換: settings が渡された場合はウォレット情報を保持
        if settings is not None:
            try:
                from eth_account import Account

                self.account = Account.from_key(settings.wallet_private_key)
                self.w3 = self._w3
                self.pool = self._pool
                self.settings = settings
                # トークンアドレスマップ（後方互換）
                if settings.usdc_address:
                    self.token_addresses = {
                        "USDC": Web3.to_checksum_address(settings.usdc_address),
                    }
            except ImportError as exc:
                raise AaveClientError(
                    "eth-account package is required. Install with: pip install eth-account"
                ) from exc

        logger.info(
            "Web3AaveClient 初期化完了 (pool=%s...%s)",
            effective_pool_address[:6],
            effective_pool_address[-4:],
        )

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        """
        Aave V3 Pool.getUserAccountData() から Health Factor を取得。

        Health Factor は 1e18 スケールで返るため Decimal に変換。
        ポジションなし（HF = type(uint256).max）の場合は Decimal("inf") を返す。

        後方互換: wallet_address が空の場合は self.account.address を使用。
        """
        # web3 はモジュールレベルで参照
        if Web3 is None:
            raise AaveClientError("web3 package is required. Install with: pip install web3")

        # 後方互換: wallet_address が未指定の場合は self.account.address を使用
        if not wallet_address and hasattr(self, "account"):
            wallet_address = self.account.address

        try:
            checksum_addr = Web3.to_checksum_address(wallet_address)
            result = self._pool.functions.getUserAccountData(checksum_addr).call()
            hf_raw: int = result[5]  # healthFactor は6番目の戻り値

            # 後方互換: HF=0 かつ totalDebtBase=0 は借入なし → inf を返す
            total_debt_base: int = result[1]
            if hf_raw == 0:
                if total_debt_base == 0:
                    logger.info("No debt position - health factor is infinite")
                    return Decimal("inf")
                else:
                    # 借入ありで HF=0 → 清算寸前の超危険状態
                    logger.warning(
                        "CRITICAL: Health factor is 0 with debt=%s - liquidation imminent!",
                        total_debt_base,
                    )
                    return Decimal("0")

            # ポジションなし = uint256 最大値
            if hf_raw >= 2**256 - 1:
                return Decimal("inf")

            # 1e18 スケールから実数へ変換（Decimal で精度保持）
            hf = Decimal(hf_raw) / Decimal(10**18)
            logger.info(
                "Health Factor 取得: wallet=%s...%s, hf=%s",
                wallet_address[:6],
                wallet_address[-4:],
                hf,
            )
            return hf

        except AaveClientError:
            raise
        except Exception as exc:
            raise AaveClientError(f"get_health_factor 失敗: {exc}") from exc

    def get_account_data(self, wallet_address: str) -> AccountData:
        """
        Aave V3 Pool.getUserAccountData() から口座データを取得。

        totalCollateralBase / totalDebtBase / availableBorrowsBase は 8 decimals (USD base unit)。
        healthFactor は 18 decimals。
        """
        if Web3 is None:
            raise AaveClientError("web3 package is required. Install with: pip install web3")

        if not wallet_address and hasattr(self, "account"):
            wallet_address = self.account.address

        try:
            checksum_addr = Web3.to_checksum_address(wallet_address)
            result = self._pool.functions.getUserAccountData(checksum_addr).call()
            # result: [totalCollateralBase, totalDebtBase, availableBorrowsBase,
            #          currentLiquidationThreshold, ltv, healthFactor]
            _BASE = Decimal(10**8)
            total_collateral_usd = Decimal(result[0]) / _BASE
            total_debt_usd = Decimal(result[1]) / _BASE
            available_borrows_usd = Decimal(result[2]) / _BASE
            hf_raw: int = result[5]
            if hf_raw >= 2**256 - 1 or (hf_raw == 0 and result[1] == 0):
                health_factor = Decimal("inf")
            else:
                health_factor = Decimal(hf_raw) / Decimal(10**18)
            return AccountData(
                total_collateral_usd=total_collateral_usd,
                total_debt_usd=total_debt_usd,
                available_borrows_usd=available_borrows_usd,
                health_factor=health_factor,
            )
        except AaveClientError:
            raise
        except Exception as exc:
            raise AaveClientError(f"get_account_data 失敗: {exc}") from exc

    def deposit(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
        # 後方互換: 旧コードは deposit(asset_symbol, amount) と呼び出す
        asset_symbol: str = "",
    ) -> "dict[str, Any] | str":
        """
        Aave V3 Pool.supply() を呼び出して deposit する。

        処理フロー:
        1. amount <= 0 チェック
        2. dry_run=True なら tx送信せず結果を返す
        3. ERC-20 decimals() で桁数取得
        4. ERC-20 approve(pool_address, amount_in_token_units)
        5. Pool.supply(asset, amount, wallet, referralCode=0)
        6. tx_hash を返す
        """
        if Web3 is None:
            raise AaveClientError("web3 package is required")

        # 後方互換: asset_symbol キーワード引数で呼ばれた場合
        if asset_symbol:
            if not hasattr(self, "token_addresses"):
                raise AaveClientError(f"Unknown asset: {asset_symbol}")
            asset_addr = self.token_addresses.get(asset_symbol)
            if not asset_addr:
                raise AaveClientError(f"Unknown asset: {asset_symbol}")
            asset_address = asset_addr
            if hasattr(self, "account"):
                wallet_address = self.account.address
            else:
                raise AaveClientError("No wallet configured")

        # 後方互換: asset_address が "0x" で始まらない場合は asset_symbol として扱う
        if asset_address and not asset_address.startswith("0x"):
            _sym = asset_address
            if not hasattr(self, "token_addresses"):
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_addr = self.token_addresses.get(_sym)
            if not asset_addr:
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_address = asset_addr
            if hasattr(self, "account"):
                wallet_address = self.account.address
            else:
                raise AaveClientError("No wallet configured")

        # amount バリデーション
        if amount <= 0:
            raise ValueError(f"deposit amount must be positive, got {amount}")

        # アドレスを安全にログ出力（末尾4文字のみ）
        logger.info(
            "deposit: asset=%s...%s, amount=%s, wallet=%s...%s, dry_run=%s",
            asset_address[:6] if asset_address else "N/A",
            asset_address[-4:] if asset_address else "N/A",
            amount,
            wallet_address[:6] if wallet_address else "N/A",
            wallet_address[-4:] if wallet_address else "N/A",
            dry_run,
        )

        if dry_run:
            return {
                "tx_hash": None,
                "amount": str(amount),
                "dry_run": True,
            }

        try:
            # ERC-20 コントラクト取得
            token_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(asset_address),
                abi=_ERC20_ABI_MINIMAL,
            )
            decimals = token_contract.functions.decimals().call()
            amount_wei = self._to_wei(amount, decimals)

            pool_address = self._pool.address

            # 署名用アカウント決定
            if hasattr(self, "account"):
                account = self.account
            else:
                from eth_account import Account

                account = Account.from_key(private_key)

            checksum_wallet = Web3.to_checksum_address(
                wallet_address if wallet_address else account.address
            )

            # Step 1: ERC-20 approve
            gas_estimator = GasEstimator(self._w3)
            approve_params_for_estimate = {
                "from": checksum_wallet,
                "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                "gasPrice": self._w3.eth.gas_price,
            }
            approve_gas = gas_estimator.estimate_gas_with_buffer(
                approve_params_for_estimate, DEFAULT_FALLBACK_GAS_APPROVE
            )
            if not gas_estimator.is_gas_cost_acceptable(approve_gas):
                raise AaveClientError(f"approve ガスコストが上限を超過: {approve_gas} units")
            approve_tx = token_contract.functions.approve(
                pool_address, amount_wei
            ).build_transaction(
                {
                    "from": checksum_wallet,
                    "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                    "gas": approve_gas,
                    "gasPrice": self._w3.eth.gas_price,
                }
            )
            signed_approve = self._w3.eth.account.sign_transaction(
                approve_tx, private_key=account.key
            )
            approve_hash = self._w3_tx.eth.send_raw_transaction(signed_approve.raw_transaction)
            self._w3.eth.wait_for_transaction_receipt(approve_hash)

            logger.info("approve tx confirmed: %s", approve_hash.hex())

            # Step 2: Pool.supply
            try:
                supply_params_for_estimate = {
                    "from": checksum_wallet,
                    "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                    "gasPrice": self._w3.eth.gas_price,
                }
                supply_gas = gas_estimator.estimate_gas_with_buffer(
                    supply_params_for_estimate, DEFAULT_FALLBACK_GAS_SUPPLY
                )
                if not gas_estimator.is_gas_cost_acceptable(supply_gas):
                    raise AaveClientError(f"supply ガスコストが上限を超過: {supply_gas} units")
                supply_tx = self._pool.functions.supply(
                    Web3.to_checksum_address(asset_address),
                    amount_wei,
                    checksum_wallet,
                    0,  # referralCode
                ).build_transaction(
                    {
                        "from": checksum_wallet,
                        "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                        "gas": supply_gas,
                        "gasPrice": self._w3.eth.gas_price,
                    }
                )
                signed_supply = self._w3.eth.account.sign_transaction(
                    supply_tx, private_key=account.key
                )
                supply_hash = self._w3_tx.eth.send_raw_transaction(signed_supply.raw_transaction)
                receipt = self._w3.eth.wait_for_transaction_receipt(supply_hash)
            except Exception as supply_exc:
                # supply 失敗時は allowance を revoke して部分成功状態を解消
                logger.error("supply 失敗: %s — allowance を revoke します", supply_exc)
                try:
                    revoke_params_for_estimate = {
                        "from": checksum_wallet,
                        "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                        "gasPrice": self._w3.eth.gas_price,
                    }
                    revoke_gas = gas_estimator.estimate_gas_with_buffer(
                        revoke_params_for_estimate, DEFAULT_FALLBACK_GAS_APPROVE
                    )
                    revoke_tx = token_contract.functions.approve(pool_address, 0).build_transaction(
                        {
                            "from": checksum_wallet,
                            "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                            "gas": revoke_gas,
                            "gasPrice": self._w3.eth.gas_price,
                        }
                    )
                    signed_revoke = self._w3.eth.account.sign_transaction(
                        revoke_tx, private_key=account.key
                    )
                    revoke_hash = self._w3_tx.eth.send_raw_transaction(
                        signed_revoke.raw_transaction
                    )
                    self._w3.eth.wait_for_transaction_receipt(revoke_hash)
                    logger.info("allowance revoke 完了: %s", revoke_hash.hex())
                except Exception as revoke_exc:
                    logger.error("allowance revoke 失敗: %s", revoke_exc)
                raise AaveClientError(f"deposit 失敗 (supply error): {supply_exc}") from supply_exc

            tx_hash_hex = receipt["transactionHash"].hex()
            logger.info(
                "deposit 完了: tx=%s, amount=%s",
                tx_hash_hex,
                amount,
            )

            return {
                "tx_hash": tx_hash_hex,
                "amount": str(amount),
                "dry_run": False,
            }

        except (AaveClientError, ValueError):
            raise

    def withdraw(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
        # 後方互換: 旧コードは withdraw(asset_symbol, amount) と呼び出す
        asset_symbol: str = "",
    ) -> "dict[str, Any] | str":
        """
        Aave V3 Pool.withdraw() を呼び出す。

        処理フロー:
        1. amount <= 0 → ValueError
        2. dry_run=True → tx送信なし
        3. get_health_factor() で HF チェック
        4. HF < 1.6 → AaveClientError("HF below threshold, withdrawal blocked")
        5. Pool.withdraw(asset, amount_wei, wallet)
        6. tx_hash を返す
        """
        if Web3 is None:
            raise AaveClientError("web3 package is required")

        # 後方互換: asset_symbol キーワード引数で呼ばれた場合
        if asset_symbol:
            if not hasattr(self, "token_addresses"):
                raise AaveClientError(f"Unknown asset: {asset_symbol}")
            asset_addr = self.token_addresses.get(asset_symbol)
            if not asset_addr:
                raise AaveClientError(f"Unknown asset: {asset_symbol}")
            asset_address = asset_addr
            if hasattr(self, "account"):
                wallet_address = self.account.address
            else:
                raise AaveClientError("No wallet configured")

        # 後方互換: asset_address が "0x" で始まらない場合は asset_symbol として扱う
        if asset_address and not asset_address.startswith("0x"):
            _sym = asset_address
            if not hasattr(self, "token_addresses"):
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_addr = self.token_addresses.get(_sym)
            if not asset_addr:
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_address = asset_addr
            if hasattr(self, "account"):
                wallet_address = self.account.address
            else:
                raise AaveClientError("No wallet configured")

        if amount <= 0:
            raise ValueError(f"withdraw amount must be positive, got {amount}")

        logger.info(
            "withdraw: asset=%s...%s, amount=%s, wallet=%s...%s, dry_run=%s",
            asset_address[:6] if asset_address else "N/A",
            asset_address[-4:] if asset_address else "N/A",
            amount,
            wallet_address[:6] if wallet_address else "N/A",
            wallet_address[-4:] if wallet_address else "N/A",
            dry_run,
        )

        if dry_run:
            return {
                "tx_hash": None,
                "amount": str(amount),
                "dry_run": True,
            }

        try:
            # CRITICAL: HF check before withdrawal (docs/13_security_design.md rule 2)
            hf = self.get_health_factor(wallet_address)
            if hf != Decimal("inf") and hf < Decimal("1.6"):
                raise AaveClientError(
                    f"HF below threshold ({hf} < 1.6), withdrawal blocked for safety"
                )

            # Get token decimals
            token_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(asset_address),
                abi=_ERC20_ABI_MINIMAL,
            )
            decimals = token_contract.functions.decimals().call()
            amount_wei = self._to_wei(amount, decimals)

            # Determine account for signing
            if hasattr(self, "account"):
                account = self.account
            else:
                from eth_account import Account

                account = Account.from_key(private_key)

            checksum_wallet = Web3.to_checksum_address(
                wallet_address if wallet_address else account.address
            )

            # Pool.withdraw(asset, amount, to)
            gas_estimator = GasEstimator(self._w3)
            withdraw_params_for_estimate = {
                "from": checksum_wallet,
                "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                "gasPrice": self._w3.eth.gas_price,
            }
            withdraw_gas = gas_estimator.estimate_gas_with_buffer(
                withdraw_params_for_estimate, DEFAULT_FALLBACK_GAS_WITHDRAW
            )
            if not gas_estimator.is_gas_cost_acceptable(withdraw_gas):
                raise AaveClientError(f"withdraw ガスコストが上限を超過: {withdraw_gas} units")
            withdraw_tx = self._pool.functions.withdraw(
                Web3.to_checksum_address(asset_address),
                amount_wei,
                checksum_wallet,
            ).build_transaction(
                {
                    "from": checksum_wallet,
                    "nonce": self._w3.eth.get_transaction_count(checksum_wallet),
                    "gas": withdraw_gas,
                    "gasPrice": self._w3.eth.gas_price,
                }
            )
            signed_tx = self._w3.eth.account.sign_transaction(withdraw_tx, private_key=account.key)
            tx_hash = self._w3_tx.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)

            tx_hash_hex = receipt["transactionHash"].hex()
            logger.info("withdraw 完了: tx=%s, amount=%s", tx_hash_hex, amount)

            return {
                "tx_hash": tx_hash_hex,
                "amount": str(amount),
                "dry_run": False,
            }

        except (AaveClientError, ValueError):
            raise
        except Exception as exc:
            raise AaveClientError(f"withdraw 失敗: {exc}") from exc

    # 後方互換: 旧 Web3AaveClient が持っていたユーティリティメソッド
    def _to_wei(self, amount: Decimal, decimals: int) -> int:
        """Decimal → Wei（最小単位）変換。"""
        return int(amount * Decimal(10**decimals))

    def _from_wei(self, amount: int, decimals: int) -> Decimal:
        """Wei（最小単位）→ Decimal 変換。"""
        return Decimal(amount) / Decimal(10**decimals)


def make_aave_client(
    client_type: str,
    rpc_url: Optional[str] = None,
    pool_address: str = _POOL_ADDRESS_SEPOLIA,
    network: str = "sepolia",
    flashbots_rpc_url: Optional[str] = None,
    chain_name: Optional[str] = None,
) -> AaveClientBase:
    """
    環境変数 AAVE_CLIENT_TYPE に基づいてクライアントを生成するファクトリ。

    Args:
        client_type: "dummy" または "web3"
        rpc_url: web3 の場合は必須
        pool_address: Aave V3 Pool コントラクトアドレス
        network: ネットワーク名 ("sepolia", "arbitrum", "arbitrum-sepolia")
        flashbots_rpc_url: Flashbots Protect RPC URL（MEV対策、オプション）
        chain_name: チェーン名（chains.py のレジストリから設定を解決する、オプション）
    """
    if client_type == "dummy":
        return DummyAaveClient()
    if client_type == "web3":
        if chain_name is not None:
            from .chains import get_chain_config, get_rpc_url_for_chain

            chain_config = get_chain_config(chain_name)
            rpc_url = get_rpc_url_for_chain(chain_config)
            pool_address = chain_config.pool_address
            flashbots_rpc_url = (
                os.getenv(chain_config.flashbots_rpc_env_var)
                if chain_config.flashbots_rpc_env_var is not None
                else None
            )
        if not rpc_url:
            raise ValueError("AAVE_CLIENT_TYPE=web3 の場合は AAVE_RPC_URL が必須です")
        _network_pool = {
            "sepolia": _POOL_ADDRESS_SEPOLIA,
            "arbitrum": _POOL_ADDRESS_ARBITRUM,
            "arbitrum-sepolia": _POOL_ADDRESS_ARBITRUM_SEPOLIA,
        }
        if pool_address == _POOL_ADDRESS_SEPOLIA and network in _network_pool:
            pool_address = _network_pool[network]
        return Web3AaveClient(
            rpc_url=rpc_url,
            pool_address=pool_address,
            flashbots_rpc_url=flashbots_rpc_url,
        )
    raise ValueError(f"不明な AAVE_CLIENT_TYPE: {client_type!r} (dummy | web3)")


def get_default_aave_client() -> AaveClient:
    """
    デフォルトの Aave クライアントを返す（後方互換）。

    環境変数 AAVE_CLIENT_TYPE で切り替え可能:
    - "web3": Web3AaveClient（実クライアント）
    - "dummy": DummyAaveClient（テスト用ダミー）

    未設定の場合は APP_ENV に応じて自動選択:
    - staging: Web3AaveClient
    - それ以外: DummyAaveClient
    """
    client_type = os.getenv("AAVE_CLIENT_TYPE")
    settings = get_aave_settings()

    if client_type == "web3":
        logger.info("Using Web3AaveClient (explicit)")
        return Web3AaveClient(settings=settings)  # type: ignore[return-value]
    elif client_type == "dummy":
        logger.info("Using DummyAaveClient (explicit)")
        return DummyAaveClient(settings=settings)  # type: ignore[return-value]
    else:
        # デフォルト: 環境に応じて自動選択
        env = os.getenv("APP_ENV", "dev")
        if env == "staging":
            logger.info("Using Web3AaveClient for staging environment")
            return Web3AaveClient(settings=settings)  # type: ignore[return-value]
        else:
            logger.info("Using DummyAaveClient for %s environment", env)
            return DummyAaveClient(settings=settings)  # type: ignore[return-value]


def make_multi_chain_clients(
    client_type: Optional[str] = None,
) -> dict[str, AaveClientBase]:
    """
    AAVE_ACTIVE_CHAINS の全チェーンに対してクライアントを生成する。

    :param client_type: "dummy" | "web3"。未指定時は AAVE_CLIENT_TYPE env var を参照。
    :returns: chain_name -> AaveClientBase のマッピング
    """
    from .chains import get_active_chains

    if client_type is None:
        client_type = os.getenv("AAVE_CLIENT_TYPE")
        if client_type is None:
            env = os.getenv("APP_ENV", "dev")
            client_type = "web3" if env == "staging" else "dummy"

    active_chains = get_active_chains()
    return {
        chain.chain_name: make_aave_client(
            client_type=client_type,
            chain_name=chain.chain_name,
        )
        for chain in active_chains
    }
