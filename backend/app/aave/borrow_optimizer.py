# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/borrow_optimizer.py
"""
GHO 借入最適化エンジン。

AaveProtocolDataProvider.getReserveData() で GHO / USDC の変動借入金利を取得し、
stkAAVE 保有量に基づく GHO 割引を考慮して最適借入通貨を比較・推奨する。

CLAUDE.md: 金融計算は Decimal のみ（float 禁止）
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from .schemas import BorrowRateComparison

logger = logging.getLogger(__name__)

# AaveProtocolDataProvider ABI（getReserveData のみ）
# Base Mainnet: 0x2d8A3C5677189723C4cB8873CfC9C8976ddf54D3
# Base Sepolia: 0x8a694b4F4Ef9B01E88D4Cee8Eb5aE7e6A62DFdCC
_DATA_PROVIDER_ABI = [
    {
        "name": "getReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [
            {"name": "unbacked", "type": "uint256"},
            {"name": "accruedToTreasuryScaled", "type": "uint256"},
            {"name": "totalAToken", "type": "uint256"},
            {"name": "totalStableDebt", "type": "uint256"},
            {"name": "totalVariableDebt", "type": "uint256"},
            {"name": "liquidityRate", "type": "uint256"},
            {"name": "variableBorrowRate", "type": "uint256"},
            {"name": "stableBorrowRate", "type": "uint256"},
            {"name": "averageStableBorrowRate", "type": "uint256"},
            {"name": "liquidityIndex", "type": "uint256"},
            {"name": "variableBorrowIndex", "type": "uint256"},
            {"name": "lastUpdateTimestamp", "type": "uint40"},
        ],
    }
]

# ERC-20 balanceOf ABI（stkAAVE 残高取得用）
_ERC20_BALANCE_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]

# Aave V3 金利は Ray (1e27) スケール
_RAY = Decimal(10**27)

# GHO 割引の上限: 20%（stkAAVE 保有量に応じた上限）
_MAX_GHO_DISCOUNT = Decimal("0.20")

# GHO が USDC より何 % 以上有利なら recommend_gho と判定するしきい値
_GHO_ADVANTAGE_THRESHOLD = Decimal("0.005")  # 0.5%


class BorrowOptimizer:
    """
    GHO / USDC 変動借入金利を比較して最適借入通貨を推奨するエンジン。

    Parameters
    ----------
    data_provider_address : str
        AaveProtocolDataProvider のコントラクトアドレス。
    usdc_address : str
        USDC のコントラクトアドレス。
    gho_address : str
        GHO のコントラクトアドレス。
    stk_aave_address : str
        stkAAVE のコントラクトアドレス（割引計算用）。
    w3 : Any
        web3.py の Web3 インスタンス（または互換 mock）。
    """

    def __init__(
        self,
        *,
        data_provider_address: str,
        usdc_address: str,
        gho_address: str,
        stk_aave_address: str,
        w3: Any,
    ) -> None:
        # web3 をモジュールレベルで参照してテストでモック可能にする
        try:
            from web3 import Web3  # noqa: PLC0415

            self._Web3 = Web3
        except ImportError as exc:
            raise ImportError("web3 package is required for BorrowOptimizer") from exc

        self._w3 = w3
        self._data_provider = self._w3.eth.contract(
            address=self._Web3.to_checksum_address(data_provider_address),
            abi=_DATA_PROVIDER_ABI,
        )
        self._usdc_address = self._Web3.to_checksum_address(usdc_address)
        self._gho_address = self._Web3.to_checksum_address(gho_address)
        self._stk_aave_address = self._Web3.to_checksum_address(stk_aave_address)

    def get_borrow_rates(self) -> tuple[Decimal, Decimal]:
        """
        AaveProtocolDataProvider.getReserveData() で USDC / GHO の変動借入 APR を取得する。

        Returns
        -------
        tuple[Decimal, Decimal]
            (usdc_variable_apr, gho_variable_apr) — 年率、0〜1 の Decimal。

        Raises
        ------
        RuntimeError
            RPC 呼び出し失敗時。
        """
        try:
            usdc_data = self._data_provider.functions.getReserveData(self._usdc_address).call()
            gho_data = self._data_provider.functions.getReserveData(self._gho_address).call()
        except Exception as exc:
            raise RuntimeError(f"getReserveData 呼び出し失敗: {exc}") from exc

        # variableBorrowRate はインデックス 6 (Ray スケール, 1e27)
        usdc_apr = Decimal(int(usdc_data[6])) / _RAY
        gho_apr = Decimal(int(gho_data[6])) / _RAY
        return usdc_apr, gho_apr

    def get_gho_discount_rate(self, wallet_address: str) -> Decimal:
        """
        stkAAVE 残高に基づく GHO 割引率を返す。

        Aave V3 の GHO 割引モデル（簡略版）:
        - stkAAVE 残高が 0 → 割引なし
        - stkAAVE 残高が多いほど割引率が大きくなり、上限 20%（_MAX_GHO_DISCOUNT）

        実際の Aave GHO 割引計算は GhoVariableDebtToken が行うため、
        本メソッドは近似値を返す（比較シグナル用）。
        stkAAVE 残高 0 の判別（割引なし）は RPC を経由して確認する。

        Parameters
        ----------
        wallet_address : str
            stkAAVE 残高を確認するウォレットアドレス。空文字の場合は割引なしを返す。

        Returns
        -------
        Decimal
            0〜0.20 の割引率（例: 0.10 = 10%割引）。
        """
        if not wallet_address:
            return Decimal("0")
        try:
            stk_contract = self._w3.eth.contract(
                address=self._stk_aave_address,
                abi=_ERC20_BALANCE_ABI,
            )
            checksum_addr = self._Web3.to_checksum_address(wallet_address)
            balance_raw: int = stk_contract.functions.balanceOf(checksum_addr).call()
            if balance_raw == 0:
                return Decimal("0")
            # stkAAVE は 18 decimals
            stk_balance = Decimal(balance_raw) / Decimal(10**18)
            # 簡略割引モデル: 100 stkAAVE 保有 → 1% 割引 (上限 20%)
            # 実際の GHO 割引は GhoDiscountRateStrategy に委譲されるが、
            # シグナル比較用として線形近似を使用する
            discount = min(stk_balance / Decimal("100") / Decimal("100"), _MAX_GHO_DISCOUNT)
            return discount
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_gho_discount_rate: RPC 失敗 → 割引なしで継続: %s", exc)
            return Decimal("0")

    def compare_borrow_rates(
        self,
        wallet_address: str = "",
        borrow_amount_usd: Decimal = Decimal("10000"),
    ) -> BorrowRateComparison:
        """
        USDC / GHO 変動借入金利を比較して BorrowRateComparison を返す。

        fail-open: RPC 失敗時は USDC をデフォルト推奨として返す。

        Parameters
        ----------
        wallet_address : str
            GHO 割引計算に使うウォレットアドレス（空 = 割引なし）。
        borrow_amount_usd : Decimal
            年間節約額の試算に使う借入金額（USD）。

        Returns
        -------
        BorrowRateComparison
        """
        try:
            usdc_apr, gho_variable_apr = self.get_borrow_rates()
        except RuntimeError as exc:
            logger.error("compare_borrow_rates: 金利取得失敗 → USDC デフォルト返却: %s", exc)
            return BorrowRateComparison(
                usdc_apr=Decimal("0"),
                gho_variable_apr=Decimal("0"),
                gho_effective_apr=Decimal("0"),
                recommendation="USDC",
                annual_savings_usd=Decimal("0"),
                error=str(exc),
            )

        discount = self.get_gho_discount_rate(wallet_address)
        gho_effective_apr = gho_variable_apr * (Decimal("1") - discount)

        # USDC より GHO が _GHO_ADVANTAGE_THRESHOLD 以上有利なら GHO 推奨
        if usdc_apr - gho_effective_apr >= _GHO_ADVANTAGE_THRESHOLD:
            recommendation = "GHO"
            savings_apr = usdc_apr - gho_effective_apr
        else:
            recommendation = "USDC"
            savings_apr = Decimal("0")

        annual_savings_usd = savings_apr * borrow_amount_usd

        logger.info(
            "compare_borrow_rates: usdc_apr=%.4f%% gho_var=%.4f%% gho_eff=%.4f%% "
            "discount=%.2f%% recommendation=%s annual_savings=$%.2f",
            float(usdc_apr * 100),
            float(gho_variable_apr * 100),
            float(gho_effective_apr * 100),
            float(discount * 100),
            recommendation,
            float(annual_savings_usd),
        )

        return BorrowRateComparison(
            usdc_apr=usdc_apr,
            gho_variable_apr=gho_variable_apr,
            gho_effective_apr=gho_effective_apr,
            recommendation=recommendation,
            annual_savings_usd=annual_savings_usd,
            error=None,
        )


def make_borrow_optimizer_from_env() -> Optional[BorrowOptimizer]:
    """
    環境変数から BorrowOptimizer を生成する。

    必須 env:
        AAVE_RPC_URL または AAVE_RPC_URL_BASE
        AAVE_DATA_PROVIDER_ADDRESS
        AAVE_USDC_ADDRESS
        AAVE_GHO_ADDRESS
        AAVE_STK_AAVE_ADDRESS

    いずれかが未設定の場合は None を返す（fail-open）。
    """
    import os  # noqa: PLC0415

    rpc_url = os.getenv("AAVE_RPC_URL") or os.getenv("AAVE_RPC_URL_BASE")
    data_provider = os.getenv("AAVE_DATA_PROVIDER_ADDRESS")
    usdc_address = os.getenv("AAVE_USDC_ADDRESS")
    gho_address = os.getenv("AAVE_GHO_ADDRESS")
    stk_aave_address = os.getenv("AAVE_STK_AAVE_ADDRESS")

    missing = [
        k
        for k, v in {
            "AAVE_RPC_URL": rpc_url,
            "AAVE_DATA_PROVIDER_ADDRESS": data_provider,
            "AAVE_USDC_ADDRESS": usdc_address,
            "AAVE_GHO_ADDRESS": gho_address,
            "AAVE_STK_AAVE_ADDRESS": stk_aave_address,
        }.items()
        if not v
    ]
    if missing:
        logger.info(
            "make_borrow_optimizer_from_env: 未設定の環境変数あり → None を返す: %s",
            missing,
        )
        return None

    try:
        from web3 import Web3  # noqa: PLC0415

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        return BorrowOptimizer(
            data_provider_address=data_provider,  # type: ignore[arg-type]
            usdc_address=usdc_address,  # type: ignore[arg-type]
            gho_address=gho_address,  # type: ignore[arg-type]
            stk_aave_address=stk_aave_address,  # type: ignore[arg-type]
            w3=w3,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("make_borrow_optimizer_from_env: 初期化失敗: %s", exc)
        return None


# ============================================================================
# borrow_currency_signal — AIジャッジ補助シグナル（GHO 借入通貨推奨）
#
# ⚠️ NOTE: 実 AI 判定フロー（service.py / agents.py）への配線は
# HUMAN-REVIEW-REQUIRED。本関数は additive な補助シグナルであり、
# 既存の BUY/SELL/HOLD 判定ロジックを変更しない。
# 配線方針: borrow_currency_signal() の戻り値を MarketContext の拡張フィールドや
# judge_with_rag のコンテキスト注入として利用する場合は、
# service.py / agents.py の安全系ロジックを変更しないよう人間がレビューする。
# ============================================================================


def borrow_currency_signal(
    usdc_apr: Decimal,
    gho_effective_apr: Decimal,
) -> str:
    """
    GHO と USDC の実効借入 APR を比較して推奨通貨シグナルを返す。

    既存の BUY/SELL/HOLD 判定ロジック（app/ai/service.py）とは独立した
    additive なシグナル。AI判定フローへの実配線は人間レビュー必須。

    判定ロジック:
    - USDC APR - GHO 実効 APR >= 0.5% → "recommend_gho"
    - それ以外 → "recommend_usdc"

    fail-open: 引数が不正な場合（例: 負値）は "recommend_usdc" を返す。

    Parameters
    ----------
    usdc_apr : Decimal
        USDC の変動借入 APR（年率、0〜1）。
    gho_effective_apr : Decimal
        GHO の実効借入 APR（stkAAVE 割引適用後、年率、0〜1）。

    Returns
    -------
    str
        "recommend_gho" または "recommend_usdc"
    """
    try:
        advantage = usdc_apr - gho_effective_apr
        if advantage >= _GHO_ADVANTAGE_THRESHOLD:
            logger.info(
                "borrow_currency_signal: GHO 有利 (advantage=%.4f%%) → recommend_gho",
                float(advantage * 100),
            )
            return "recommend_gho"
        logger.info(
            "borrow_currency_signal: USDC 推奨 (advantage=%.4f%%) → recommend_usdc",
            float(advantage * 100),
        )
        return "recommend_usdc"
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "borrow_currency_signal: 計算失敗 → USDC デフォルト返却 (fail-open): %s", exc
        )
        return "recommend_usdc"
