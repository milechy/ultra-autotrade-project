# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/reward_claimer.py
"""
Aave V3 リワード自動 Claim + 複利再投資モジュール。

UiIncentiveDataProviderV3.getFullReservesIncentiveData() で未請求 AAVE/GHO
リワードを取得し、$5 以上なら 24h ごとに自動 Claim → Aave に再供給する。

Security Rules (docs/13_security_design.md):
- 金融計算は Decimal のみ (float 禁止)
- 秘密鍵は env のみ
- Provider 呼び出し失敗時は fail-open (例外を伝播させない)
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Claim を実行する最低 USD 閾値
CLAIM_THRESHOLD_USD = Decimal("5.00")

# Claim の最小間隔（時間）
CLAIM_INTERVAL_HOURS = 24

# UiIncentiveDataProviderV3 ABI (最小限: getUserReservesIncentivesData)
_UI_INCENTIVE_PROVIDER_ABI = [
    {
        "inputs": [
            {
                "internalType": "contract IPoolAddressesProvider",
                "name": "provider",
                "type": "address",
            },
            {"internalType": "address", "name": "user", "type": "address"},
        ],
        "name": "getUserReservesIncentivesData",
        "outputs": [
            {
                "components": [
                    {"internalType": "address", "name": "underlyingAsset", "type": "address"},
                    {
                        "components": [
                            {"internalType": "address", "name": "tokenAddress", "type": "address"},
                            {
                                "internalType": "address",
                                "name": "incentiveControllerAddress",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "string",
                                        "name": "rewardTokenSymbol",
                                        "type": "string",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "rewardTokenAddress",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "rewardOracleAddress",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "emissionPerSecond",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "incentivesLastUpdateTimestamp",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "tokenIncentivesUserIndex",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "emissionEndTimestamp",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "int256",
                                        "name": "rewardPriceFeed",
                                        "type": "int256",
                                    },
                                    {
                                        "internalType": "uint8",
                                        "name": "rewardTokenDecimals",
                                        "type": "uint8",
                                    },
                                    {"internalType": "uint8", "name": "precision", "type": "uint8"},
                                    {
                                        "internalType": "uint8",
                                        "name": "priceFeedDecimals",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "userUnclaimedRewards",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "bytes32",
                                        "name": "rewardTokenId",
                                        "type": "bytes32",
                                    },
                                ],
                                "internalType": "struct IUiIncentiveDataProviderV3.UserRewardInfo[]",
                                "name": "userRewardsInformation",
                                "type": "tuple[]",
                            },
                        ],
                        "internalType": "struct IUiIncentiveDataProviderV3.UserIncentiveData",
                        "name": "aTokenIncentivesUserData",
                        "type": "tuple",
                    },
                    {
                        "components": [
                            {"internalType": "address", "name": "tokenAddress", "type": "address"},
                            {
                                "internalType": "address",
                                "name": "incentiveControllerAddress",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "string",
                                        "name": "rewardTokenSymbol",
                                        "type": "string",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "rewardTokenAddress",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "rewardOracleAddress",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "emissionPerSecond",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "incentivesLastUpdateTimestamp",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "tokenIncentivesUserIndex",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "emissionEndTimestamp",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "int256",
                                        "name": "rewardPriceFeed",
                                        "type": "int256",
                                    },
                                    {
                                        "internalType": "uint8",
                                        "name": "rewardTokenDecimals",
                                        "type": "uint8",
                                    },
                                    {"internalType": "uint8", "name": "precision", "type": "uint8"},
                                    {
                                        "internalType": "uint8",
                                        "name": "priceFeedDecimals",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "userUnclaimedRewards",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "bytes32",
                                        "name": "rewardTokenId",
                                        "type": "bytes32",
                                    },
                                ],
                                "internalType": "struct IUiIncentiveDataProviderV3.UserRewardInfo[]",
                                "name": "userRewardsInformation",
                                "type": "tuple[]",
                            },
                        ],
                        "internalType": "struct IUiIncentiveDataProviderV3.UserIncentiveData",
                        "name": "vTokenIncentivesUserData",
                        "type": "tuple",
                    },
                    {
                        "components": [
                            {"internalType": "address", "name": "tokenAddress", "type": "address"},
                            {
                                "internalType": "address",
                                "name": "incentiveControllerAddress",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "string",
                                        "name": "rewardTokenSymbol",
                                        "type": "string",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "rewardTokenAddress",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "rewardOracleAddress",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "emissionPerSecond",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "incentivesLastUpdateTimestamp",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "tokenIncentivesUserIndex",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "emissionEndTimestamp",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "int256",
                                        "name": "rewardPriceFeed",
                                        "type": "int256",
                                    },
                                    {
                                        "internalType": "uint8",
                                        "name": "rewardTokenDecimals",
                                        "type": "uint8",
                                    },
                                    {"internalType": "uint8", "name": "precision", "type": "uint8"},
                                    {
                                        "internalType": "uint8",
                                        "name": "priceFeedDecimals",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "userUnclaimedRewards",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "bytes32",
                                        "name": "rewardTokenId",
                                        "type": "bytes32",
                                    },
                                ],
                                "internalType": "struct IUiIncentiveDataProviderV3.UserRewardInfo[]",
                                "name": "userRewardsInformation",
                                "type": "tuple[]",
                            },
                        ],
                        "internalType": "struct IUiIncentiveDataProviderV3.UserIncentiveData",
                        "name": "sTokenIncentivesUserData",
                        "type": "tuple",
                    },
                ],
                "internalType": "struct IUiIncentiveDataProviderV3.UserReservesIncentivesData[]",
                "name": "",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    }
]

# RewardsController ABI (claimAllRewards + getAllUserRewards)
_REWARDS_CONTROLLER_ABI = [
    {
        "inputs": [
            {"internalType": "address[]", "name": "assets", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
        ],
        "name": "claimAllRewards",
        "outputs": [
            {"internalType": "address[]", "name": "rewardsList", "type": "address[]"},
            {"internalType": "uint256[]", "name": "claimedAmounts", "type": "uint256[]"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# web3 は optional 依存（テスト時はモック可）
try:
    from web3 import Web3
except ImportError:
    Web3 = None  # type: ignore[assignment,misc]


class RewardClaimer:
    """
    Aave V3 リワード自動 Claim + 複利再投資クラス。

    UiIncentiveDataProviderV3 で未請求リワードを取得し、
    CLAIM_THRESHOLD_USD 以上なら claimAllRewards -> supply で再投資する。

    コンストラクタ引数で外部コントラクトを注入可能にしているため、
    テスト時は全て Mock に差し替えてオンチェーン呼び出しを排除できる。
    """

    def __init__(
        self,
        w3: Any,
        ui_incentive_provider_address: str,
        rewards_controller_address: str,
        pool_addresses_provider: str,
        aave_client: Any,
        usdc_address: Optional[str] = None,
    ) -> None:
        self._w3 = w3
        self._ui_provider_address = ui_incentive_provider_address
        self._rewards_controller_address = rewards_controller_address
        self._pool_addresses_provider = pool_addresses_provider
        self._aave_client = aave_client
        self._usdc_address = usdc_address

        if Web3 is not None:
            self._ui_provider = w3.eth.contract(
                address=Web3.to_checksum_address(ui_incentive_provider_address),
                abi=_UI_INCENTIVE_PROVIDER_ABI,
            )
            self._rewards_controller = w3.eth.contract(
                address=Web3.to_checksum_address(rewards_controller_address),
                abi=_REWARDS_CONTROLLER_ABI,
            )

    def get_claimable_rewards(self, wallet_address: str) -> list[dict[str, Any]]:
        """
        wallet の未請求リワード一覧を取得する。

        Returns:
            list of dict with keys:
                asset_name: str
                reward_token_address: str
                amount: Decimal
                amount_usd: Decimal

        Provider 呼び出し失敗時は [] を返す (fail-open)。
        金融計算は Decimal のみ。
        """
        if Web3 is None:
            logger.warning("get_claimable_rewards: web3 not available, returning []")
            return []

        try:
            checksum_wallet = Web3.to_checksum_address(wallet_address)
            checksum_provider = Web3.to_checksum_address(self._pool_addresses_provider)

            raw_data = self._ui_provider.functions.getUserReservesIncentivesData(
                checksum_provider, checksum_wallet
            ).call()

            # 各 aToken / vToken / sToken のリワード情報を集約
            rewards_map: dict[str, dict[str, Any]] = {}

            for reserve_entry in raw_data:
                # reserve_entry: (underlyingAsset, aTokenIncentives, vTokenIncentives, sTokenIncentives)
                for token_incentives in reserve_entry[1:4]:
                    user_rewards_info = token_incentives[2]
                    for reward_info in user_rewards_info:
                        # Index: 0=symbol, 1=tokenAddr, 7=priceFeed(int256),
                        #        8=tokenDecimals, 10=priceFeedDecimals, 11=userUnclaimedRewards
                        symbol: str = reward_info[0]
                        token_addr: str = reward_info[1]
                        unclaimed_raw: int = int(reward_info[11])
                        token_decimals: int = int(reward_info[8])
                        price_feed_raw: int = int(reward_info[7])
                        price_feed_decimals: int = int(reward_info[10])

                        if unclaimed_raw <= 0:
                            continue

                        amount = Decimal(unclaimed_raw) / Decimal(10**token_decimals)
                        if price_feed_raw <= 0:
                            amount_usd = Decimal("0")
                        else:
                            price_usd = Decimal(price_feed_raw) / Decimal(10**price_feed_decimals)
                            amount_usd = amount * price_usd

                        key = token_addr.lower()
                        if key in rewards_map:
                            rewards_map[key]["amount"] += amount
                            rewards_map[key]["amount_usd"] += amount_usd
                        else:
                            rewards_map[key] = {
                                "asset_name": symbol,
                                "reward_token_address": token_addr,
                                "amount": amount,
                                "amount_usd": amount_usd,
                            }

            result = list(rewards_map.values())
            logger.info(
                "get_claimable_rewards: wallet=%s...%s, found=%d tokens",
                wallet_address[:6] if wallet_address else "",
                wallet_address[-4:] if wallet_address else "",
                len(result),
            )
            return result

        except Exception as exc:  # noqa: BLE001
            logger.warning("get_claimable_rewards: Provider 呼び出し失敗 (fail-open): %s", exc)
            return []

    def _total_usd(self, rewards: list[dict[str, Any]]) -> Decimal:
        """リワード一覧の合計 USD を Decimal で計算。"""
        total = Decimal("0")
        for r in rewards:
            total += r["amount_usd"]
        return total

    def claim_all_rewards(
        self,
        wallet_address: str,
        private_key: str,
        asset_addresses: list[str],
        dry_run: bool = False,
    ) -> Optional[str]:
        """
        RewardsController.claimAllRewards() を呼び出してリワードを Claim する。

        Returns:
            tx_hash (str) or None (dry_run)

        Raises:
            RuntimeError: web3 未インストール時 / tx 失敗時
        """
        if Web3 is None:
            raise RuntimeError("web3 package is required for claim_all_rewards")

        if dry_run:
            logger.info(
                "claim_all_rewards (dry_run): wallet=%s...%s",
                wallet_address[:6] if wallet_address else "",
                wallet_address[-4:] if wallet_address else "",
            )
            return None

        try:
            from eth_account import Account  # noqa: PLC0415

            account = Account.from_key(private_key)
            checksum_wallet = Web3.to_checksum_address(wallet_address)
            checksum_assets = [Web3.to_checksum_address(a) for a in asset_addresses]

            nonce = int(self._w3.eth.get_transaction_count(checksum_wallet, "pending"))
            gas_price = self._w3.eth.gas_price
            chain_id = self._w3.eth.chain_id

            tx = self._rewards_controller.functions.claimAllRewards(
                checksum_assets,
                checksum_wallet,
            ).build_transaction(
                {
                    "from": checksum_wallet,
                    "nonce": nonce,
                    "gasPrice": gas_price,
                    "chainId": chain_id,
                }
            )
            try:
                estimated_gas = self._w3.eth.estimate_gas(tx)
                tx["gas"] = int(Decimal(estimated_gas) * Decimal("12") // Decimal("10"))
            except Exception as gas_exc:  # noqa: BLE001
                logger.warning(
                    "claim_all_rewards: gas estimation failed: %s, using fallback", gas_exc
                )
                tx["gas"] = 300_000

            signed = self._w3.eth.account.sign_transaction(tx, private_key=account.key)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            self._w3.eth.wait_for_transaction_receipt(tx_hash)
            tx_hash_hex: str = str(tx_hash.hex())
            logger.info(
                "claim_all_rewards: tx=%s, wallet=%s...%s",
                tx_hash_hex,
                wallet_address[:6] if wallet_address else "",
                wallet_address[-4:] if wallet_address else "",
            )
            return tx_hash_hex
        except Exception as exc:
            raise RuntimeError(f"claim_all_rewards 失敗: {exc}") from exc

    def auto_claim_if_worthy(
        self,
        wallet_address: str,
        private_key: str,
        asset_addresses: Optional[list[str]] = None,
        usdc_asset_address: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        未請求リワードを取得し、閾値 ($5) 以上なら Claim -> supply で再投資する。

        例外を伝播させない (fail-open)。

        Returns:
            dict: claimed, total_usd, rewards, supply_tx_hash, skip_reason, error
        """
        result: dict[str, Any] = {
            "claimed": False,
            "total_usd": "0",
            "rewards": [],
            "supply_tx_hash": None,
            "skip_reason": None,
            "error": None,
        }

        try:
            rewards = self.get_claimable_rewards(wallet_address)
            total_usd = self._total_usd(rewards)
            result["total_usd"] = str(total_usd)
            result["rewards"] = rewards

            if total_usd < CLAIM_THRESHOLD_USD:
                skip_msg = (
                    f"合計 USD ({total_usd}) が閾値 ({CLAIM_THRESHOLD_USD}) 未満のためスキップ"
                )
                logger.info("auto_claim_if_worthy: %s", skip_msg)
                result["skip_reason"] = skip_msg
                return result

            _asset_addresses = asset_addresses or []
            self.claim_all_rewards(
                wallet_address=wallet_address,
                private_key=private_key,
                asset_addresses=_asset_addresses,
                dry_run=dry_run,
            )
            result["claimed"] = True

            _usdc_addr = usdc_asset_address or self._usdc_address
            if _usdc_addr and not dry_run:
                try:
                    supply_result = self._aave_client.deposit(
                        asset_address=_usdc_addr,
                        amount=total_usd,
                        wallet_address=wallet_address,
                        private_key=private_key,
                        dry_run=False,
                    )
                    if isinstance(supply_result, dict):
                        result["supply_tx_hash"] = supply_result.get("tx_hash")
                    logger.info(
                        "auto_claim_if_worthy: supply 完了 total_usd=%s wallet=%s...%s",
                        total_usd,
                        wallet_address[:6] if wallet_address else "",
                        wallet_address[-4:] if wallet_address else "",
                    )
                except Exception as supply_exc:  # noqa: BLE001
                    logger.warning("auto_claim_if_worthy: supply 失敗 (fail-open): %s", supply_exc)
                    result["error"] = f"supply 失敗: {supply_exc}"
            elif dry_run:
                logger.info("auto_claim_if_worthy: dry_run=True のため supply スキップ")

            return result

        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_claim_if_worthy: 予期しないエラー (fail-open): %s", exc)
            result["error"] = str(exc)
            return result


def make_reward_claimer_from_env() -> Optional[RewardClaimer]:
    """
    環境変数から RewardClaimer を生成する。

    FLAG: AAVE_UI_INCENTIVE_PROVIDER_ADDRESS / AAVE_REWARDS_CONTROLLER_ADDRESS /
          AAVE_POOL_ADDRESSES_PROVIDER が未設定の場合は None を返す。
    """
    try:
        if Web3 is None:
            logger.warning("make_reward_claimer_from_env: web3 not available")
            return None

        rpc_url = os.getenv("AAVE_RPC_URL")
        ui_provider_addr = os.getenv("AAVE_UI_INCENTIVE_PROVIDER_ADDRESS")
        rewards_ctrl_addr = os.getenv("AAVE_REWARDS_CONTROLLER_ADDRESS")
        pool_provider_addr = os.getenv("AAVE_POOL_ADDRESSES_PROVIDER")
        usdc_address = os.getenv("AAVE_USDC_ADDRESS")

        if not all([rpc_url, ui_provider_addr, rewards_ctrl_addr, pool_provider_addr]):
            logger.info("make_reward_claimer_from_env: 必須 env 未設定 -> None を返す")
            return None

        from .client import make_aave_client  # noqa: PLC0415

        client_type = os.getenv("AAVE_CLIENT_TYPE", "dummy")
        aave_client = make_aave_client(client_type=client_type, rpc_url=rpc_url)
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        return RewardClaimer(
            w3=w3,
            ui_incentive_provider_address=ui_provider_addr,  # type: ignore[arg-type]
            rewards_controller_address=rewards_ctrl_addr,  # type: ignore[arg-type]
            pool_addresses_provider=pool_provider_addr,  # type: ignore[arg-type]
            aave_client=aave_client,
            usdc_address=usdc_address,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("make_reward_claimer_from_env: 生成失敗 (fail-open): %s", exc)
        return None
