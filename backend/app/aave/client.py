# backend/app/aave/client.py

"""
Aave とのやり取りを行うクライアント層。

- DummyAaveClient: テスト・開発用のダミークライアント
- Web3AaveClient: Aave V3 の実クライアント（Polygon Mumbai テストネット対応）
"""

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol

from .config import AaveSettings, get_aave_settings

logger = logging.getLogger(__name__)


class AaveClientError(Exception):
    """Aave クライアント全般の基底例外。"""


class AaveTransactionError(AaveClientError):
    """トランザクション送信・実行エラー。"""


class AaveClient(Protocol):
    """
    Aave クライアントのインターフェース。

    deposit / withdraw / get_health_factor を備えた実装であれば差し替え可能。
    """

    def get_health_factor(self) -> Optional[Decimal]:
        """現在のポジションのヘルスファクターを返す。"""

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        """
        指定したトークンを Aave に deposit する。

        :return: トランザクションハッシュ
        """

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        """
        指定したトークンを Aave から withdraw する。

        :return: トランザクションハッシュ
        """


@dataclass
class DummyAaveClient:
    """
    テスト・開発用のダミー Aave クライアント。

    - 実ネットワークには一切アクセスしない
    - ヘルスファクターは常に安全側の値（例: 2.0）を返す
    - deposit / withdraw は tx_hash 風の文字列を返すだけ
    """

    settings: AaveSettings

    def get_health_factor(self) -> Decimal:
        # 安全側の固定値。実装時にはここを本物の値に差し替える。
        return Decimal("2.0")

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        return f"dummy-deposit-{asset_symbol}-{amount}"

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        return f"dummy-withdraw-{asset_symbol}-{amount}"


class Web3AaveClient:
    """
    Aave V3 の実クライアント実装（Polygon Mumbai テストネット対応）。

    責務:
    - Web3 経由で Aave Pool コントラクトと通信
    - deposit（supply）/ withdraw / getHealthFactor の実行
    - トランザクション署名・送信

    NOTE:
    - Aave V3 では deposit は supply() 関数に変更されている
    - healthFactor は 1e18 スケール（1.0 = 1e18）
    """

    # Aave V3 Pool の簡易 ABI（必要な関数のみ）
    POOL_ABI = [
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
    ]

    # ERC20 トークンの簡易 ABI
    ERC20_ABI = [
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
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "address", "name": "owner", "type": "address"},
                {"internalType": "address", "name": "spender", "type": "address"},
            ],
            "name": "allowance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
    ]

    def __init__(self, settings: Optional[AaveSettings] = None):
        """
        Web3AaveClient を初期化する。

        Args:
            settings: AaveSettings インスタンス。省略時は環境変数から取得。

        Raises:
            AaveClientError: RPC 接続失敗、または必須設定が不足している場合
        """
        # web3 は遅延インポート（テスト時にモックしやすくするため）
        try:
            from eth_account import Account
            from web3 import Web3
        except ImportError as exc:
            raise AaveClientError(
                "web3 and eth-account packages are required. "
                "Install with: pip install web3 eth-account"
            ) from exc

        self.settings = settings or get_aave_settings()

        # 必須設定のチェック
        if not self.settings.rpc_url:
            raise AaveClientError("AAVE_RPC_URL is required for Web3AaveClient")
        if not self.settings.wallet_private_key:
            raise AaveClientError("AAVE_WALLET_PRIVATE_KEY is required for Web3AaveClient")
        if not self.settings.pool_address:
            raise AaveClientError("AAVE_POOL_ADDRESS is required for Web3AaveClient")
        if not self.settings.usdc_address:
            raise AaveClientError("AAVE_USDC_ADDRESS is required for Web3AaveClient")

        # Web3 接続
        self.w3 = Web3(Web3.HTTPProvider(self.settings.rpc_url))
        if not self.w3.is_connected():
            raise AaveClientError(f"Failed to connect to RPC: {self.settings.rpc_url}")

        # ウォレット
        self.account = Account.from_key(self.settings.wallet_private_key)
        logger.info("Web3AaveClient initialized with wallet: %s", self.account.address)

        # コントラクト
        self.pool = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.settings.pool_address),
            abi=self.POOL_ABI,
        )

        # トークンアドレスマップ
        self.token_addresses = {
            "USDC": Web3.to_checksum_address(self.settings.usdc_address),
        }

    def _get_token_contract(self, asset_symbol: str):
        """トークンコントラクトを取得する。"""
        from web3 import Web3

        token_address = self.token_addresses.get(asset_symbol)
        if not token_address:
            raise AaveClientError(f"Unknown asset symbol: {asset_symbol}")

        return self.w3.eth.contract(
            address=token_address,
            abi=self.ERC20_ABI,
        )

    def _to_wei(self, amount: Decimal, decimals: int) -> int:
        """Decimal → Wei（最小単位）変換。"""
        return int(amount * Decimal(10**decimals))

    def _from_wei(self, amount: int, decimals: int) -> Decimal:
        """Wei（最小単位）→ Decimal 変換。"""
        return Decimal(amount) / Decimal(10**decimals)

    def get_health_factor(self) -> Optional[Decimal]:
        """
        現在のヘルスファクターを取得する。

        Returns:
            Decimal: ヘルスファクター値（0 以上）
            None: 借入なしの場合（ヘルスファクター無限大として扱う）

        Raises:
            AaveClientError: コントラクト呼び出しに失敗した場合

        Note:
            - HF=0 かつ totalDebtBase > 0 は清算寸前の超危険状態
            - この場合は None ではなく Decimal('0') を返す（fail-closed 原則）
            - MonitoringService が緊急停止を発動できるようにするため
        """
        try:
            user_data = self.pool.functions.getUserAccountData(
                self.account.address
            ).call()

            # getUserAccountData の戻り値:
            # (totalCollateralBase, totalDebtBase, availableBorrowsBase,
            #  currentLiquidationThreshold, ltv, healthFactor)
            total_debt_base = user_data[1]
            health_factor_raw = user_data[5]

            if health_factor_raw == 0:
                if total_debt_base == 0:
                    # 借入なし → ヘルスファクター無限大として扱う
                    logger.info("No debt position - health factor is infinite")
                    return None
                else:
                    # 借入ありで HF=0 → 清算寸前の超危険状態
                    # fail-closed: 緊急停止を発動させるため 0 を返す
                    logger.warning(
                        "CRITICAL: Health factor is 0 with debt=%s - liquidation imminent!",
                        total_debt_base,
                    )
                    return Decimal("0")

            # Aave V3 では healthFactor は 1e18 スケール（1.0 = 1e18）
            health_factor = Decimal(health_factor_raw) / Decimal(10**18)
            logger.info("Current health factor: %s", health_factor)
            return health_factor

        except Exception as exc:
            logger.error("Failed to get health factor: %s", exc)
            raise AaveClientError(f"Failed to get health factor: {exc}") from exc

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        """
        指定したトークンを Aave に deposit（supply）する。

        手順:
        1. トークンの approve（既に十分な allowance がある場合はスキップ）
        2. Pool.supply() 実行

        Args:
            asset_symbol: トークンシンボル（例: "USDC"）
            amount: 預入額（人間が読める単位、例: 10.5 USDC）

        Returns:
            str: supply トランザクションハッシュ

        Raises:
            AaveTransactionError: トランザクション失敗時
        """
        try:
            token = self._get_token_contract(asset_symbol)
            decimals = token.functions.decimals().call()
            amount_wei = self._to_wei(amount, decimals)

            logger.info(
                "Depositing %s %s (wei: %d) to Aave",
                amount,
                asset_symbol,
                amount_wei,
            )

            # 現在の allowance をチェック
            current_allowance = token.functions.allowance(
                self.account.address,
                self.pool.address,
            ).call()

            # 1. Approve（必要な場合のみ）
            if current_allowance < amount_wei:
                logger.info("Approving %s for Aave Pool...", asset_symbol)
                approve_tx = token.functions.approve(
                    self.pool.address,
                    amount_wei,
                ).build_transaction(
                    {
                        "from": self.account.address,
                        "nonce": self.w3.eth.get_transaction_count(self.account.address),
                        "gas": 100000,
                        "gasPrice": self.w3.eth.gas_price,
                    }
                )

                signed_approve = self.account.sign_transaction(approve_tx)
                approve_hash = self.w3.eth.send_raw_transaction(
                    signed_approve.raw_transaction
                )
                self.w3.eth.wait_for_transaction_receipt(approve_hash)
                logger.info("Approve tx: %s", approve_hash.hex())

            # 2. Supply
            logger.info("Supplying %s to Aave Pool...", asset_symbol)
            supply_tx = self.pool.functions.supply(
                token.address,
                amount_wei,
                self.account.address,
                0,  # referralCode
            ).build_transaction(
                {
                    "from": self.account.address,
                    "nonce": self.w3.eth.get_transaction_count(self.account.address),
                    "gas": 300000,
                    "gasPrice": self.w3.eth.gas_price,
                }
            )

            signed_supply = self.account.sign_transaction(supply_tx)
            supply_hash = self.w3.eth.send_raw_transaction(signed_supply.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(supply_hash)

            if receipt.status != 1:
                raise AaveTransactionError(
                    f"Supply transaction failed: {supply_hash.hex()}"
                )

            logger.info("Supply tx successful: %s", supply_hash.hex())
            return supply_hash.hex()

        except AaveTransactionError:
            raise
        except Exception as exc:
            logger.error("Deposit failed: %s", exc)
            raise AaveTransactionError(f"Deposit failed: {exc}") from exc

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        """
        指定したトークンを Aave から withdraw する。

        Args:
            asset_symbol: トークンシンボル（例: "USDC"）
            amount: 引出額（人間が読める単位、例: 10.5 USDC）

        Returns:
            str: withdraw トランザクションハッシュ

        Raises:
            AaveTransactionError: トランザクション失敗時
        """
        try:
            token = self._get_token_contract(asset_symbol)
            decimals = token.functions.decimals().call()
            amount_wei = self._to_wei(amount, decimals)

            logger.info(
                "Withdrawing %s %s (wei: %d) from Aave",
                amount,
                asset_symbol,
                amount_wei,
            )

            withdraw_tx = self.pool.functions.withdraw(
                token.address,
                amount_wei,
                self.account.address,
            ).build_transaction(
                {
                    "from": self.account.address,
                    "nonce": self.w3.eth.get_transaction_count(self.account.address),
                    "gas": 300000,
                    "gasPrice": self.w3.eth.gas_price,
                }
            )

            signed_withdraw = self.account.sign_transaction(withdraw_tx)
            withdraw_hash = self.w3.eth.send_raw_transaction(
                signed_withdraw.raw_transaction
            )
            receipt = self.w3.eth.wait_for_transaction_receipt(withdraw_hash)

            if receipt.status != 1:
                raise AaveTransactionError(
                    f"Withdraw transaction failed: {withdraw_hash.hex()}"
                )

            logger.info("Withdraw tx successful: %s", withdraw_hash.hex())
            return withdraw_hash.hex()

        except AaveTransactionError:
            raise
        except Exception as exc:
            logger.error("Withdraw failed: %s", exc)
            raise AaveTransactionError(f"Withdraw failed: {exc}") from exc


def get_default_aave_client() -> AaveClient:
    """
    デフォルトの Aave クライアントを返す。

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
        return Web3AaveClient(settings=settings)
    elif client_type == "dummy":
        logger.info("Using DummyAaveClient (explicit)")
        return DummyAaveClient(settings=settings)
    else:
        # デフォルト: 環境に応じて自動選択
        env = os.getenv("APP_ENV", "dev")
        if env == "staging":
            logger.info("Using Web3AaveClient for staging environment")
            return Web3AaveClient(settings=settings)
        else:
            logger.info("Using DummyAaveClient for %s environment", env)
            return DummyAaveClient(settings=settings)
