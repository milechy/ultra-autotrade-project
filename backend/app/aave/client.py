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
from typing import Any, Optional, Protocol, cast

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
    from web3.types import Nonce
except ImportError:
    Web3 = None  # type: ignore[assignment,misc]
    Nonce = int  # type: ignore[assignment,misc]

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
    {
        "name": "getReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {
                        "name": "configuration",
                        "type": "tuple",
                        "components": [{"name": "data", "type": "uint256"}],
                    },
                    {"name": "liquidityIndex", "type": "uint128"},
                    {"name": "currentLiquidityRate", "type": "uint128"},
                    {"name": "variableBorrowIndex", "type": "uint128"},
                    {"name": "currentVariableBorrowRate", "type": "uint128"},
                    {"name": "currentStableBorrowRate", "type": "uint128"},
                    {"name": "lastUpdateTimestamp", "type": "uint40"},
                    {"name": "id", "type": "uint16"},
                    {"name": "aTokenAddress", "type": "address"},
                    {"name": "stableDebtTokenAddress", "type": "address"},
                    {"name": "variableDebtTokenAddress", "type": "address"},
                    {"name": "interestRateStrategyAddress", "type": "address"},
                    {"name": "accruedToTreasury", "type": "uint128"},
                    {"name": "unbacked", "type": "uint128"},
                    {"name": "isolationModeTotalDebt", "type": "uint128"},
                ],
            }
        ],
    },
]

# ERC-20 totalSupply ABI（利用率計算用）
_ERC20_TOTAL_SUPPLY_ABI = [
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    }
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

# Aave V3 Pool アドレス（Base Mainnet） — chains.py registry の base.pool_address と一致
_POOL_ADDRESS_BASE_MAINNET = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"

# Aave V3 Pool アドレス（Base Sepolia） — chains.py registry の base_sepolia.pool_address と一致
_POOL_ADDRESS_BASE_SEPOLIA = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"


class _NonceTracker:
    """1 フロー内の連続 tx に対してローカルに nonce を管理するトラッカー。

    Alchemy/Infura などの RPC ノードは複数ノード構成で書き込み反映にラグがあり、
    approve 送信直後に get_transaction_count() を呼ぶと stale (旧 nonce) が返り
    supply が "nonce too low" / "replacement underpriced" で失敗する事故が起きる
    (2026-04-22 インシデント)。対策として同一フロー内では以下を行う:

    1. `get_transaction_count(wallet, "pending")` を一度だけ呼ぶ (mempool-aware)
    2. `peek()` で現在の nonce を覗いて tx を build
    3. send_raw_transaction が成功してから `advance()` で次の値に進める

    send_raw_transaction が失敗した場合は nonce 未消費のため advance を呼ばない。
    ブロックチェーンに tx が含まれた後 (receipt が revert) は nonce 消費済みだが、
    その場合も送信自体は成功しているため本 tracker 上は既に advance 済みで整合する。
    """

    def __init__(self, w3: Any, wallet: str) -> None:
        self._w3 = w3
        self._wallet = wallet
        # "pending" フラグで mempool に積まれた tx も考慮した最新 nonce を取得
        self._current: int = int(w3.eth.get_transaction_count(wallet, "pending"))
        self._start: int = self._current
        logger.info(
            "nonce tracker initialized: wallet=%s...%s, start_nonce=%d",
            wallet[:6] if wallet else "",
            wallet[-4:] if wallet else "",
            self._current,
        )

    def peek(self) -> Nonce:
        """次に build_transaction に渡すべき nonce を返す (消費しない)。"""
        return cast(Nonce, self._current)

    def advance(self) -> None:
        """send_raw_transaction が成功した後に呼び出して nonce を 1 進める。"""
        self._current += 1
        logger.debug(
            "nonce advanced: wallet=%s...%s, next_nonce=%d, consumed=%d",
            self._wallet[:6] if self._wallet else "",
            self._wallet[-4:] if self._wallet else "",
            self._current,
            self._current - self._start,
        )

    @property
    def start(self) -> int:
        """トラッカー初期化時の nonce (テスト/監査用)。"""
        return self._start

    @property
    def consumed(self) -> int:
        """これまでに advance された回数 (= 送信成功した tx 数)。"""
        return self._current - self._start


@dataclass
class AccountData:
    """Aave V3 account data from getUserAccountData()."""

    total_collateral_usd: Decimal
    total_debt_usd: Decimal
    available_borrows_usd: Decimal
    health_factor: Decimal
    # currentLiquidationThreshold (BPS → ratio): result[3] / 10000
    # DummyAaveClient は 0.80 固定。Web3AaveClient は RPC から実値を取得。
    liquidation_threshold: Optional[Decimal] = None


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

    def get_pool_utilization(self, asset_symbol: str) -> Optional[Decimal]:
        """プール利用率 (0-100) を返す。取得不可の場合は None。

        サブクラスがオーバーライドしない場合は None を返す（fail-open）。
        """
        return None


class AaveClientError(Exception):
    """Aave クライアントの基底例外。"""


class AaveBlocklistedAssetError(AaveClientError):
    """
    ブラックリスト登録済みアセットへの deposit を試みた場合に raise される。

    2026-06 rsETH/srsETH/wrsETH エクスプロイト再発防止。
    config.BLOCKLISTED_COLLATERAL に登録されたシンボルが対象。
    大文字小文字非依存 (rseth/RSETH 等も含む)。
    """


class OracleDeviationHardStopError(AaveClientError):
    """
    Oracle 多重検証で price deviation >= 閾値 (デフォルト 2%) を検知した場合に raise される。

    3価格 (Chainlink / Pyth / Uniswap V3 TWAP) が全て揃った状態で乖離超過時のみ発動。
    価格ソースが 2 件以下の場合は fail-open（従来通り継続）。
    """


# 後方互換: 旧コードが AaveTransactionError を参照している箇所のため維持
class AaveTransactionError(AaveClientError):
    """トランザクション送信・実行エラー。"""


# 後方互換: service.py が AaveClient Protocol を使っているため維持
class AaveClient(Protocol):
    """
    Aave クライアントのインターフェース（後方互換 Protocol）。

    deposit / withdraw / get_health_factor を備えた実装であれば差し替え可能。
    """

    def get_health_factor(self, wallet_address: str = "") -> Optional[Decimal]:
        """現在のポジションのヘルスファクターを返す。空の場合はクライアントのデフォルトを使用。"""

    def deposit(self, asset_symbol: str, amount: Decimal, wallet_address: str = "") -> str:
        """指定したトークンを Aave に deposit する。"""

    def withdraw(self, asset_symbol: str, amount: Decimal, wallet_address: str = "") -> str:
        """指定したトークンを Aave から withdraw する。"""

    def build_deposit_txs(
        self, asset_symbol: str, amount: Decimal, wallet_address: str
    ) -> "dict[str, Any]":
        """パートナー署名用: 未署名の approve + supply トランザクションを返す。"""

    def build_withdraw_tx(
        self, asset_symbol: str, amount: Decimal, wallet_address: str
    ) -> "dict[str, Any]":
        """パートナー署名用: 未署名の withdraw トランザクションを返す。"""

    def get_account_data(self, wallet_address: str) -> "AccountData":
        """Aave V3 Pool のアカウントデータを取得する。"""

    def get_pool_utilization(self, asset_symbol: str) -> Optional[Decimal]:
        """プール利用率 (0-100) を返す。取得不可の場合は None。"""


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
            liquidation_threshold=Decimal("0.80"),
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

    def build_deposit_txs(
        self,
        asset_symbol: str,
        amount: Decimal,
        wallet_address: str,
    ) -> "dict[str, Any]":
        return {
            "approve_tx": {
                "to": "0xDUMMY",
                "data": "0x",
                "from": wallet_address,
                "chainId": 84532,
                "value": "0x0",
            },
            "supply_tx": {
                "to": "0xDUMMY",
                "data": "0x",
                "from": wallet_address,
                "chainId": 84532,
                "value": "0x0",
            },
        }

    def build_withdraw_tx(
        self,
        asset_symbol: str,
        amount: Decimal,
        wallet_address: str,
    ) -> "dict[str, Any]":
        return {
            "withdraw_tx": {
                "to": "0xDUMMY",
                "data": "0x",
                "from": wallet_address,
                "chainId": 84532,
                "value": "0x0",
            }
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
        pool_address: Optional[str] = None,
        settings: Optional[AaveSettings] = None,
        flashbots_rpc_url: Optional[str] = None,
        token_addresses: Optional[dict[str, str]] = None,
    ) -> None:
        # 2026-05-01: pool_address のデフォルトを Sepolia hardcode から None に変更。
        # 旧デフォルトは mainnet 切替後に silent regression (testnet pool に書き込み) を
        # 起こすため、env (AAVE_POOL_ADDRESS) または引数の明示を必須化する。
        # web3 はモジュールレベルで参照（テスト時にモックしやすくするため）
        if Web3 is None:
            raise AaveClientError("web3 package is required. Install with: pip install web3")

        # 後方互換: settings から rpc_url/pool_address を取得することもできる
        # wallet_private_key は read-only ユースケース (Indicator Agent / shadow mode) のため任意化。
        # 署名 tx (supply/withdraw) は呼出時に fail-fast する。v4 §14「backend wallet 持たない」設計と整合。
        if settings is not None:
            if not settings.rpc_url:
                raise AaveClientError("AAVE_RPC_URL is required for Web3AaveClient")
            if not settings.pool_address:
                raise AaveClientError("AAVE_POOL_ADDRESS is required for Web3AaveClient")
            if not settings.usdc_address:
                raise AaveClientError("AAVE_USDC_ADDRESS is required for Web3AaveClient")
            effective_rpc_url = settings.rpc_url
            effective_pool_address = settings.pool_address
        else:
            if not rpc_url:
                raise AaveClientError("AAVE_RPC_URL is required for Web3AaveClient")
            if pool_address is None:
                pool_address = os.getenv("AAVE_POOL_ADDRESS")
                if not pool_address:
                    raise AaveClientError(
                        "AAVE_POOL_ADDRESS env var or pool_address argument is "
                        "required for Web3AaveClient"
                    )
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
        # NOTE: 旧コードは self._w3.is_connected() を二重 health check していたが、
        # web3.py 7.x の Web3.is_connected() は内部で `web3_clientVersion` RPC を呼ぶ。
        # Base Sepolia 公式 public RPC (https://sepolia.base.org) 等の一部 RPC は
        # この method を未サポート → False 返却 → false positive で AaveClientError。
        # RPCProvider.get_web3() 内で既に `eth.block_number` で疎通確認済みなので、
        # 二重チェックは削除して RPCProvider を単一責任の疎通判定窓口とする。
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
        # wallet_private_key が未設定なら self.account は設定せず、read-only クライアントとして動作。
        # supply/withdraw は呼出時に getattr(self, "account", None) 経由で fail-fast する。
        if settings is not None:
            self.w3 = self._w3
            self.pool = self._pool
            self.settings = settings
            # トークンアドレスマップ（後方互換）
            if settings.usdc_address:
                self.token_addresses = {
                    "USDC": Web3.to_checksum_address(settings.usdc_address),
                }
            if settings.wallet_private_key:
                try:
                    from eth_account import Account

                    self.account = Account.from_key(settings.wallet_private_key)
                except ImportError as exc:
                    raise AaveClientError(
                        "eth-account package is required. Install with: pip install eth-account"
                    ) from exc
            else:
                logger.info(
                    "Web3AaveClient: wallet_private_key 未設定 → read-only モードで起動 "
                    "(supply/withdraw は呼出時に fail-fast)"
                )

        # マルチチェーン経路（settings 無し）での token_addresses 配線。
        # make_aave_client(chain_name=...) が chains.py の chain_config.tokens を渡す。
        # これが無いと build_deposit_txs / build_withdraw_tx が hasattr ガードで
        # "Unknown asset" を投げ、non-custodial partner 署名フロー (build-tx) が
        # 500 になる（2026-06-02 launch ブロッカー修正）。
        # settings 経路が既に self.token_addresses を設定済みの場合は上書きしない。
        if token_addresses and not hasattr(self, "token_addresses"):
            self.token_addresses = {
                symbol: Web3.to_checksum_address(addr) for symbol, addr in token_addresses.items()
            }

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
            # currentLiquidationThreshold は BPS (basis points, e.g. 8000 = 80%)
            lt_raw: int = result[3]
            liquidation_threshold: Optional[Decimal] = (
                Decimal(lt_raw) / Decimal("10000") if lt_raw > 0 else Decimal("0.75")
            )
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
                liquidation_threshold=liquidation_threshold,
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

        # ブラックリストチェック（rsETH/srsETH/wrsETH エクスプロイト再発防止 2026-06）
        # 大文字小文字非依存: asset.upper() を BLOCKLISTED_COLLATERAL_UPPER と比較。
        # rseth / RSETH / Rseth 等も確実にブロックする。
        from .config import BLOCKLISTED_COLLATERAL_UPPER  # noqa: PLC0415

        _check_sym = asset_symbol or (asset_address if not asset_address.startswith("0x") else "")
        if _check_sym and _check_sym.upper() in BLOCKLISTED_COLLATERAL_UPPER:
            raise AaveBlocklistedAssetError(
                f"asset '{_check_sym}' はブラックリスト登録済みのため deposit 不可"
            )

        # Oracle 乖離チェック（S-1: 3ソース全揃いで乖離 >= 2% の場合のみ HARD_STOP）
        # シンボルが確定している場合（asset_symbol または非0x文字列 asset_address）のみ実行。
        if _check_sym:
            _oracle_cfg = _load_oracle_config_for_asset(_check_sym)
            if _oracle_cfg is not None:
                from .oracle_checker import check_price_deviation  # noqa: PLC0415

                _oracle_result = check_price_deviation(
                    asset=_check_sym,
                    chainlink_feed_address=_oracle_cfg.get("chainlink_feed"),
                    rpc_url=_oracle_cfg.get("rpc_url"),
                    pyth_api_url=_oracle_cfg.get("pyth_api_url"),
                    pyth_price_id=_oracle_cfg.get("pyth_price_id"),
                    uniswap_pool_address=_oracle_cfg.get("uniswap_pool"),
                )
                _available = sum(
                    1
                    for p in [
                        _oracle_result.chainlink_price,
                        _oracle_result.pyth_price,
                        _oracle_result.twap_price,
                    ]
                    if p is not None
                )
                if _oracle_result.level == "HARD_STOP" and _available >= 3:  # noqa: PLR2004
                    raise OracleDeviationHardStopError(
                        f"[{_check_sym}] Oracle 価格乖離 {_oracle_result.max_deviation_pct:.4f}% "
                        "が閾値を超過 (3ソース確認済) — deposit HARD_STOP"
                    )

        # 後方互換: asset_symbol キーワード引数で呼ばれた場合
        if asset_symbol:
            if not hasattr(self, "token_addresses"):
                raise AaveClientError(f"Unknown asset: {asset_symbol}")
            asset_addr = self.token_addresses.get(asset_symbol)
            if not asset_addr:
                raise AaveClientError(f"Unknown asset: {asset_symbol}")
            asset_address = asset_addr
            # NULL wallet guard (Layer 3): execute 経路ではデフォルト wallet fallback を使わない
            if not wallet_address:
                raise AaveClientError(
                    "wallet_address is required for on-chain deposit: "
                    "default account fallback disabled on execute paths"
                )

        # 後方互換: asset_address が "0x" で始まらない場合は asset_symbol として扱う
        if asset_address and not asset_address.startswith("0x"):
            _sym = asset_address
            if not hasattr(self, "token_addresses"):
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_addr = self.token_addresses.get(_sym)
            if not asset_addr:
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_address = asset_addr
            # NULL wallet guard (Layer 3): execute 経路ではデフォルト wallet fallback を使わない
            if not wallet_address:
                raise AaveClientError(
                    "wallet_address is required for on-chain deposit: "
                    "default account fallback disabled on execute paths"
                )

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

        # 署名 tx (非 dry_run) 経路では signer 必須。
        # __init__ 時の wallet_private_key を任意化したため、ここで明示 fail-fast。
        if not getattr(self, "account", None) and not private_key:
            raise AaveClientError(
                "AAVE_WALLET_PRIVATE_KEY (or private_key arg) is required for signed supply tx"
            )

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

            # NULL wallet guard (Layer 3 final): 空 wallet で on-chain 操作に到達したら raise
            if not wallet_address:
                raise AaveClientError(
                    "wallet_address is required for on-chain deposit: "
                    "default account fallback disabled on execute paths"
                )
            checksum_wallet = Web3.to_checksum_address(wallet_address)

            # approve → supply (→ revoke on failure) は同一フローの連続 tx。
            # RPC ノードの nonce 伝播遅延を避けるためローカル tracker で明示的に管理する。
            nonce_tracker = _NonceTracker(self._w3, checksum_wallet)

            gas_estimator = GasEstimator(self._w3)

            # Step 1: ERC-20 approve — gas estimation は nonce 消費前に実行 (失敗時 fail-fast)
            approve_params_for_estimate = {
                "from": checksum_wallet,
                "nonce": nonce_tracker.peek(),
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
                    "nonce": nonce_tracker.peek(),
                    "gas": approve_gas,
                    "gasPrice": self._w3.eth.gas_price,
                }
            )
            signed_approve = self._w3.eth.account.sign_transaction(
                approve_tx, private_key=account.key
            )
            approve_hash = self._w3_tx.eth.send_raw_transaction(signed_approve.raw_transaction)
            # 送信成功 → nonce 消費済みとして tracker を進める。
            # 以降 supply が失敗しても revoke 側が正しい nonce を使えるよう、
            # wait_for_receipt より前に advance する。
            nonce_tracker.advance()
            self._w3.eth.wait_for_transaction_receipt(approve_hash)

            logger.info("approve tx confirmed: %s", approve_hash.hex())

            # Step 2: Pool.supply
            try:
                supply_params_for_estimate = {
                    "from": checksum_wallet,
                    "nonce": nonce_tracker.peek(),
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
                        "nonce": nonce_tracker.peek(),
                        "gas": supply_gas,
                        "gasPrice": self._w3.eth.gas_price,
                    }
                )
                signed_supply = self._w3.eth.account.sign_transaction(
                    supply_tx, private_key=account.key
                )
                supply_hash = self._w3_tx.eth.send_raw_transaction(signed_supply.raw_transaction)
                # send 成功 → nonce 消費。receipt が revert しても nonce 自体は消費される
                # (tx はブロックに含まれる) ため、このタイミングで advance しておく。
                nonce_tracker.advance()
                receipt = self._w3.eth.wait_for_transaction_receipt(supply_hash)
            except Exception as supply_exc:
                # supply 失敗時は allowance を revoke して部分成功状態を解消。
                # nonce_tracker.peek() は supply の成否に応じた正しい値を返す:
                #   - supply の build/send_raw が失敗 → advance されていないので approve+1
                #   - supply 送信成功で receipt が revert → advance 済みなので approve+2
                logger.error("supply 失敗: %s — allowance を revoke します", supply_exc)
                try:
                    revoke_params_for_estimate = {
                        "from": checksum_wallet,
                        "nonce": nonce_tracker.peek(),
                        "gasPrice": self._w3.eth.gas_price,
                    }
                    revoke_gas = gas_estimator.estimate_gas_with_buffer(
                        revoke_params_for_estimate, DEFAULT_FALLBACK_GAS_APPROVE
                    )
                    revoke_tx = token_contract.functions.approve(pool_address, 0).build_transaction(
                        {
                            "from": checksum_wallet,
                            "nonce": nonce_tracker.peek(),
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
                    nonce_tracker.advance()
                    self._w3.eth.wait_for_transaction_receipt(revoke_hash)
                    logger.info("allowance revoke 完了: %s", revoke_hash.hex())
                except Exception as revoke_exc:
                    logger.error(
                        "allowance revoke 失敗: %s (nonce_consumed=%d, start=%d)",
                        revoke_exc,
                        nonce_tracker.consumed,
                        nonce_tracker.start,
                    )
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
            # NULL wallet guard (Layer 3): execute 経路ではデフォルト wallet fallback を使わない
            if not wallet_address:
                raise AaveClientError(
                    "wallet_address is required for on-chain withdraw: "
                    "default account fallback disabled on execute paths"
                )

        # 後方互換: asset_address が "0x" で始まらない場合は asset_symbol として扱う
        if asset_address and not asset_address.startswith("0x"):
            _sym = asset_address
            if not hasattr(self, "token_addresses"):
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_addr = self.token_addresses.get(_sym)
            if not asset_addr:
                raise AaveClientError(f"Unknown asset: {_sym}")
            asset_address = asset_addr
            # NULL wallet guard (Layer 3): execute 経路ではデフォルト wallet fallback を使わない
            if not wallet_address:
                raise AaveClientError(
                    "wallet_address is required for on-chain withdraw: "
                    "default account fallback disabled on execute paths"
                )

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

        # 署名 tx (非 dry_run) 経路では signer 必須。
        # __init__ 時の wallet_private_key を任意化したため、ここで明示 fail-fast。
        if not getattr(self, "account", None) and not private_key:
            raise AaveClientError(
                "AAVE_WALLET_PRIVATE_KEY (or private_key arg) is required for signed withdraw tx"
            )

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

            # NULL wallet guard (Layer 3 final): 空 wallet で on-chain 操作に到達したら raise
            if not wallet_address:
                raise AaveClientError(
                    "wallet_address is required for on-chain withdraw: "
                    "default account fallback disabled on execute paths"
                )
            checksum_wallet = Web3.to_checksum_address(wallet_address)

            # withdraw は単発 tx だが mempool-aware な nonce (pending) を使うため tracker を経由する。
            nonce_tracker = _NonceTracker(self._w3, checksum_wallet)

            # Pool.withdraw(asset, amount, to)
            gas_estimator = GasEstimator(self._w3)
            withdraw_params_for_estimate = {
                "from": checksum_wallet,
                "nonce": nonce_tracker.peek(),
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
                    "nonce": nonce_tracker.peek(),
                    "gas": withdraw_gas,
                    "gasPrice": self._w3.eth.gas_price,
                }
            )
            signed_tx = self._w3.eth.account.sign_transaction(withdraw_tx, private_key=account.key)
            tx_hash = self._w3_tx.eth.send_raw_transaction(signed_tx.raw_transaction)
            nonce_tracker.advance()
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

    def build_deposit_txs(
        self,
        asset_symbol: str,
        amount: Decimal,
        wallet_address: str,
    ) -> "dict[str, Any]":
        """
        パートナー本人署名用: 未署名の approve + supply トランザクションを構築して返す。

        サーバー鍵では署名しない。フロントエンドが Privy sendTransaction() で送信する。

        Returns:
            {
                "approve_tx": {to, data, from, chainId, value},
                "supply_tx": {to, data, from, chainId, value},
            }
        """
        if Web3 is None:
            raise AaveClientError("web3 package is required")
        if not wallet_address:
            raise AaveClientError("wallet_address は必須です (partner 署名)")

        # ブラックリストチェック（rsETH/srsETH/wrsETH エクスプロイト再発防止 2026-06）
        # deposit() と同じチェックを build_deposit_txs() にも適用（パートナー署名フロー経路）。
        # 大文字小文字非依存: .upper() で正規化して比較。
        from .config import BLOCKLISTED_COLLATERAL_UPPER  # noqa: PLC0415

        if asset_symbol.upper() in BLOCKLISTED_COLLATERAL_UPPER:
            raise AaveBlocklistedAssetError(
                f"asset '{asset_symbol}' はブラックリスト登録済みのため deposit 不可"
            )

        # Oracle 乖離チェック（S-1: 3ソース全揃いで乖離 >= 2% の場合のみ HARD_STOP）
        # fail-open 方針: 価格ソースが 2 件以下の場合はブロックせず継続。
        # 3ソース揃って乖離超過した場合のみ OracleDeviationHardStopError を raise する。
        _oracle_cfg = _load_oracle_config_for_asset(asset_symbol)
        if _oracle_cfg is not None:
            from .oracle_checker import check_price_deviation  # noqa: PLC0415

            _oracle_result = check_price_deviation(
                asset=asset_symbol,
                chainlink_feed_address=_oracle_cfg.get("chainlink_feed"),
                rpc_url=_oracle_cfg.get("rpc_url"),
                pyth_api_url=_oracle_cfg.get("pyth_api_url"),
                pyth_price_id=_oracle_cfg.get("pyth_price_id"),
                uniswap_pool_address=_oracle_cfg.get("uniswap_pool"),
            )
            # 3ソース全揃いで HARD_STOP の場合のみブロック（fail-open 遵守）
            _available = sum(
                1
                for p in [
                    _oracle_result.chainlink_price,
                    _oracle_result.pyth_price,
                    _oracle_result.twap_price,
                ]
                if p is not None
            )
            if _oracle_result.level == "HARD_STOP" and _available >= 3:  # noqa: PLR2004
                raise OracleDeviationHardStopError(
                    f"[{asset_symbol}] Oracle 価格乖離 {_oracle_result.max_deviation_pct:.4f}% "
                    "が閾値を超過 (3ソース確認済) — deposit HARD_STOP"
                )

        # asset_symbol → address 解決
        if not hasattr(self, "token_addresses"):
            raise AaveClientError(f"Unknown asset: {asset_symbol}")
        asset_address = self.token_addresses.get(asset_symbol)
        if not asset_address:
            raise AaveClientError(f"Unknown asset: {asset_symbol}")

        token_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(asset_address),
            abi=_ERC20_ABI_MINIMAL,
        )
        decimals = token_contract.functions.decimals().call()
        amount_wei = self._to_wei(amount, decimals)
        checksum_wallet = Web3.to_checksum_address(wallet_address)
        pool_address = self._pool.address
        chain_id = self._w3.eth.chain_id

        # web3.py v7: Contract.encodeABI() は廃止され encode_abi() に改名
        # (fn_name= キーワードも abi_element_identifier 位置引数に変更)。
        approve_data = token_contract.encode_abi("approve", args=[pool_address, amount_wei])
        supply_data = self._pool.encode_abi(
            "supply",
            args=[Web3.to_checksum_address(asset_address), amount_wei, checksum_wallet, 0],
        )

        return {
            "approve_tx": {
                "to": Web3.to_checksum_address(asset_address),
                "data": approve_data,
                "from": checksum_wallet,
                "chainId": chain_id,
                "value": "0x0",
            },
            "supply_tx": {
                "to": str(pool_address),
                "data": supply_data,
                "from": checksum_wallet,
                "chainId": chain_id,
                "value": "0x0",
            },
        }

    def build_withdraw_tx(
        self,
        asset_symbol: str,
        amount: Decimal,
        wallet_address: str,
    ) -> "dict[str, Any]":
        """
        パートナー本人署名用: 未署名の withdraw トランザクションを構築して返す。

        Returns:
            {"withdraw_tx": {to, data, from, chainId, value}}
        """
        if Web3 is None:
            raise AaveClientError("web3 package is required")
        if not wallet_address:
            raise AaveClientError("wallet_address は必須です (partner 署名)")

        if not hasattr(self, "token_addresses"):
            raise AaveClientError(f"Unknown asset: {asset_symbol}")
        asset_address = self.token_addresses.get(asset_symbol)
        if not asset_address:
            raise AaveClientError(f"Unknown asset: {asset_symbol}")

        token_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(asset_address),
            abi=_ERC20_ABI_MINIMAL,
        )
        decimals = token_contract.functions.decimals().call()
        amount_wei = self._to_wei(amount, decimals)
        checksum_wallet = Web3.to_checksum_address(wallet_address)
        chain_id = self._w3.eth.chain_id

        # web3.py v7: encodeABI → encode_abi（fn_name= → 位置引数）
        withdraw_data = self._pool.encode_abi(
            "withdraw",
            args=[Web3.to_checksum_address(asset_address), amount_wei, checksum_wallet],
        )

        return {
            "withdraw_tx": {
                "to": str(self._pool.address),
                "data": withdraw_data,
                "from": checksum_wallet,
                "chainId": chain_id,
                "value": "0x0",
            }
        }

    def get_pool_utilization(self, asset_symbol: str) -> Optional[Decimal]:
        """Aave V3 プールの現在利用率 (0-100) を返す。

        getReserveData → aToken.totalSupply / vDebtToken.totalSupply で計算。
        RPC失敗・アドレス未設定の場合は None を返す（fail-open）。
        """
        if Web3 is None:
            return None
        if not hasattr(self, "token_addresses"):
            logger.warning("get_pool_utilization: token_addresses not set; skipping check")
            return None
        asset_addr = self.token_addresses.get(asset_symbol)
        if not asset_addr:
            logger.warning(
                "get_pool_utilization: unknown asset_symbol=%s; skipping check", asset_symbol
            )
            return None
        try:
            reserve_data = self._pool.functions.getReserveData(
                Web3.to_checksum_address(asset_addr)
            ).call()
            atoken_addr: str = reserve_data[8]
            sdebt_addr: str = reserve_data[9]
            vdebt_addr: str = reserve_data[10]

            atoken_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(atoken_addr),
                abi=_ERC20_TOTAL_SUPPLY_ABI,
            )
            atoken_total = int(atoken_contract.functions.totalSupply().call())

            vdebt_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(vdebt_addr),
                abi=_ERC20_TOTAL_SUPPLY_ABI,
            )
            vdebt_total = int(vdebt_contract.functions.totalSupply().call())

            # V3.3+ でstable debt は廃止済み。ゼロアドレスの場合はcallしない
            if int(sdebt_addr, 16) == 0:
                sdebt_total = 0
            else:
                sdebt_contract = self._w3.eth.contract(
                    address=Web3.to_checksum_address(sdebt_addr),
                    abi=_ERC20_TOTAL_SUPPLY_ABI,
                )
                sdebt_total = int(sdebt_contract.functions.totalSupply().call())

            total_debt = vdebt_total + sdebt_total
            if atoken_total <= 0:
                return Decimal("0")
            utilization_pct = Decimal(total_debt) / Decimal(atoken_total) * Decimal(100)
            logger.debug(
                "get_pool_utilization: %s utilization=%.2f%%",
                asset_symbol,
                float(utilization_pct),
            )
            return utilization_pct
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_pool_utilization: RPC failed for %s: %s", asset_symbol, exc)
            return None

    # 後方互換: 旧 Web3AaveClient が持っていたユーティリティメソッド
    def _to_wei(self, amount: Decimal, decimals: int) -> int:
        """Decimal → Wei（最小単位）変換。"""
        return int(amount * Decimal(10**decimals))

    def _from_wei(self, amount: int, decimals: int) -> Decimal:
        """Wei（最小単位）→ Decimal 変換。"""
        return Decimal(amount) / Decimal(10**decimals)


def _load_oracle_config_for_asset(asset_symbol: str) -> "dict[str, Any] | None":
    """
    AAVE_ORACLE_ASSETS_JSON 環境変数から対象 asset のオラクル設定を返す。

    設定がない場合や JSON パースエラー時は None を返す (fail-open)。
    build_deposit_txs() のオラクル乖離チェックで使用する。
    """
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415

    raw = os.getenv("AAVE_ORACLE_ASSETS_JSON", "[]")
    try:
        configs: list[dict[str, Any]] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    for cfg in configs:
        if isinstance(cfg, dict) and cfg.get("asset", "").upper() == asset_symbol.upper():
            return cfg
    return None


def make_aave_client(
    client_type: str,
    rpc_url: Optional[str] = None,
    pool_address: Optional[str] = None,
    network: Optional[str] = None,
    flashbots_rpc_url: Optional[str] = None,
    chain_name: Optional[str] = None,
) -> AaveClientBase:
    """
    環境変数 AAVE_CLIENT_TYPE に基づいてクライアントを生成するファクトリ。

    Args:
        client_type: "dummy" または "web3"
        rpc_url: web3 の場合は必須
        pool_address: Aave V3 Pool コントラクトアドレス。未指定時は network 経由 or
            AAVE_POOL_ADDRESS env から解決
        network: ネットワーク名 ("sepolia", "arbitrum", "arbitrum-sepolia",
            "base", "base_sepolia")。未指定時は AAVE_NETWORK env を参照
        flashbots_rpc_url: Flashbots Protect RPC URL（MEV対策、オプション）
        chain_name: チェーン名（chains.py のレジストリから設定を解決する、オプション）

    2026-05-01: pool_address / network のデフォルトを Sepolia hardcode から
    None に変更。silent testnet regression (mainnet 切替後に sepolia に書き込む)
    の防止が目的。Base Mainnet (chain 8453) を _network_pool に追加。
    """
    if client_type == "dummy":
        return DummyAaveClient()
    if client_type == "web3":
        # chain_config.tokens を client に配線するためのマップ（chain_name 経路のみ）。
        # 未配線だと build_deposit_txs / build_withdraw_tx が "Unknown asset" を投げる。
        token_addresses: Optional[dict[str, str]] = None
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
            token_addresses = chain_config.tokens
        if not rpc_url:
            raise ValueError("AAVE_CLIENT_TYPE=web3 の場合は AAVE_RPC_URL が必須です")

        # network 未指定時は env (AAVE_NETWORK) から解決
        if network is None:
            network = os.getenv("AAVE_NETWORK")

        _network_pool = {
            "sepolia": _POOL_ADDRESS_SEPOLIA,
            "arbitrum": _POOL_ADDRESS_ARBITRUM,
            "arbitrum-sepolia": _POOL_ADDRESS_ARBITRUM_SEPOLIA,
            "base": _POOL_ADDRESS_BASE_MAINNET,
            "base_sepolia": _POOL_ADDRESS_BASE_SEPOLIA,
        }
        # pool_address 未指定 + network 既知 → network から解決
        if pool_address is None and network is not None and network in _network_pool:
            pool_address = _network_pool[network]
        client = Web3AaveClient(
            rpc_url=rpc_url,
            pool_address=pool_address,
            flashbots_rpc_url=flashbots_rpc_url,
            token_addresses=token_addresses,
        )
        # chain_name 経由時は chain config のトークンアドレスを注入する。
        # Web3AaveClient.__init__ は settings=None の場合に token_addresses を設定しないため
        # build_deposit_txs / build_withdraw_tx が "Unknown asset" で失敗する (method2 バグ修正)。
        if token_addresses and not hasattr(client, "token_addresses"):
            client.token_addresses = {
                sym: Web3.to_checksum_address(addr) for sym, addr in token_addresses.items()
            }
        return client
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

    RPC URL 未設定のチェーンは警告ログを出力してスキップする（ValueError で起動失敗しない）。

    :param client_type: "dummy" | "web3"。未指定時は AAVE_CLIENT_TYPE env var を参照。
    :returns: chain_name -> AaveClientBase のマッピング（RPC 未設定チェーンは含まれない）
    """
    from .chains import get_active_chains

    if client_type is None:
        client_type = os.getenv("AAVE_CLIENT_TYPE")
        if client_type is None:
            env = os.getenv("APP_ENV", "dev")
            client_type = "web3" if env == "staging" else "dummy"

    active_chains = get_active_chains()
    result: dict[str, AaveClientBase] = {}
    for chain in active_chains:
        # web3 モードでは RPC 未設定チェーンをスキップ（本番は AAVE_ACTIVE_CHAINS=base のみ想定）
        if client_type == "web3" and not os.getenv(chain.rpc_url_env_var):
            logger.warning(
                "Skipping chain %r: RPC URL env var %r is not set",
                chain.chain_name,
                chain.rpc_url_env_var,
            )
            continue
        result[chain.chain_name] = make_aave_client(
            client_type=client_type,
            chain_name=chain.chain_name,
        )
    return result


# ==============================================================================
# build-tx 本人一致 検証 (P0-3 / Asana 1215364095372268)
#
# Privy Policy Engine は onBehalfOf == msg.sender の動的自己参照比較を未サポート
# (value は静的リテラルのみ) のため、本人一致は build-tx 側固定 + 署名前 calldata
# 再検証で担保する。以下はサーバーが生成済み calldata を実デコードして
# onBehalfOf / to が本人 wallet であることを確認する純粋関数 (RPC 不要)。
#
# build_partner_tx エンドポイントが署名前 hook (補完層) として呼び、
# 不一致なら未署名 tx をフロントに返さず reject する。
# ==============================================================================


class OnBehalfMismatchError(AaveClientError):
    """生成済み calldata の onBehalfOf / to が本人 wallet と不一致のとき送出。"""


def _decode_pool_calldata(calldata: str) -> "tuple[str, dict[str, Any]]":
    """Aave V3 Pool の calldata を実デコードして (関数名, 引数 dict) を返す。

    provider 不要 (ABI デコードはオフライン処理)。web3 未インストール時は
    AaveClientError を送出する。
    """
    if Web3 is None:
        raise AaveClientError("web3 package is required")
    # provider 無し Web3 インスタンスでも decode_function_input は動作する
    pool = Web3().eth.contract(abi=_POOL_ABI_MINIMAL)
    func, params = pool.decode_function_input(calldata)
    return func.fn_name, dict(params)


def verify_supply_onbehalf(supply_calldata: str, expected_wallet: str) -> bool:
    """supply calldata の onBehalfOf が expected_wallet と一致するか検証する。

    一致時のみ True。関数が supply でない / onBehalfOf 不一致 / デコード不能なら
    False (fail-closed)。比較は checksum 正規化して大文字小文字非依存。
    expected_wallet の値の中身には依存しない (常に渡された本人 wallet と照合)。
    """
    try:
        fn_name, params = _decode_pool_calldata(supply_calldata)
    except Exception:
        return False
    if fn_name != "supply":
        return False
    on_behalf = params.get("onBehalfOf")
    if not on_behalf:
        return False
    try:
        return Web3.to_checksum_address(on_behalf) == Web3.to_checksum_address(expected_wallet)
    except Exception:
        return False


def verify_withdraw_to(withdraw_calldata: str, expected_wallet: str) -> bool:
    """withdraw calldata の to が expected_wallet と一致するか検証する (fail-closed)。"""
    try:
        fn_name, params = _decode_pool_calldata(withdraw_calldata)
    except Exception:
        return False
    if fn_name != "withdraw":
        return False
    to_addr = params.get("to")
    if not to_addr:
        return False
    try:
        return Web3.to_checksum_address(to_addr) == Web3.to_checksum_address(expected_wallet)
    except Exception:
        return False
