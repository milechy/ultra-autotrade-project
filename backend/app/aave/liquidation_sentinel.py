# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/liquidation_sentinel.py
"""
清算リスク事前計算（ストレステスト）とプール赤字蓄積の早期検知。

- get_stress_test(): 価格 -10%/-20% 時の Health Factor を事前計算する。
- PoolHealthMonitor.check_pool_deficits(): getReserveDeficit() でプール赤字を監視し、
  閾値超過時に Slack アラートを発火する。

セキュリティ: docs/13_security_design.md
- 金融計算は Decimal のみ（float 禁止）
- ログにウォレットアドレスを出さない（マスク必須）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

# プール赤字アラートの閾値（USD 建て）
DEFICIT_ALERT_THRESHOLD = Decimal("10000")

# 監視対象のデフォルトアセットシンボル
# NOTE: USDC のみとしている理由:
#   WETH / wstETH は getReserveDeficit() がトークン単位 (18 decimals) で返すが、
#   Price Oracle 統合なしでは「1 トークン = 1 USD」と扱うことになり、
#   実際の USD 価値（例: 1 WETH ≈ $3000）より桁違いに小さい値で閾値比較してしまい
#   アラートが実質不発火になる安全上の問題がある。
#   WETH / wstETH は Aave Price Oracle 統合後に追加する。（TODO: oracle integration）
DEFAULT_DEFICIT_TOKENS = ["USDC"]


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class StressTestScenario:
    """価格ドロップ率 pct に対するストレステスト結果。"""

    price_drop_pct: Decimal
    """価格下落率（例: 10% 下落 → Decimal("0.10")）"""

    simulated_hf: Optional[Decimal]
    """シミュレーション後の Health Factor。計算不能時は None。"""

    collateral_after_usd: Optional[Decimal]
    """価格下落後の担保 USD 評価額。"""


@dataclass
class StressTestResult:
    """
    ウォレットのストレステスト結果。

    GET /api/aave/stress-test のレスポンスに使用する。
    """

    wallet_address: str
    current_hf: Optional[Decimal]
    current_collateral_usd: Optional[Decimal]
    current_debt_usd: Optional[Decimal]
    liquidation_threshold: Optional[Decimal]
    scenarios: list[StressTestScenario] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class PoolDeficitInfo:
    """アセット単位のプール赤字情報。"""

    asset_symbol: str
    deficit_usd: Decimal
    alert_triggered: bool


@dataclass
class PoolHealthReport:
    """
    プール全体の赤字ヘルスレポート。

    GET /api/aave/pool-health のレスポンスに使用する。
    """

    chain_name: str
    deficits: list[PoolDeficitInfo] = field(default_factory=list)
    total_deficit_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    alert_triggered: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# ストレステストロジック
# ---------------------------------------------------------------------------


def simulate_hf_at_price_drop(
    collateral_usd: Decimal,
    debt_usd: Decimal,
    liquidation_threshold: Decimal,
    price_drop_pct: Decimal,
) -> Optional[Decimal]:
    """
    価格下落後の Health Factor を計算する。

    HF = (collateral * (1 - price_drop_pct) * liquidation_threshold) / debt

    Args:
        collateral_usd: 現在の担保 USD 評価額（Decimal）
        debt_usd: 現在の総借入 USD（Decimal）
        liquidation_threshold: 清算しきい値（例: 0.80 = 80%）
        price_drop_pct: 価格下落率（0 <= pct < 1。例: 0.10 = 10%）

    Returns:
        Decimal: 計算後の HF。debt=0 の場合は None（清算なし）。

    Raises:
        ValueError: price_drop_pct が [0, 1) の範囲外の場合。
    """
    if not (Decimal("0") <= price_drop_pct < Decimal("1")):
        raise ValueError(
            f"price_drop_pct は 0 以上 1 未満の Decimal である必要があります。got: {price_drop_pct}"
        )

    if debt_usd <= Decimal("0"):
        # 借入なし = 清算リスクなし
        return None

    price_factor = Decimal("1") - price_drop_pct
    adjusted_collateral = collateral_usd * price_factor * liquidation_threshold

    try:
        hf = adjusted_collateral / debt_usd
    except InvalidOperation:
        logger.warning(
            "simulate_hf_at_price_drop: Decimal 計算失敗 collateral=%s debt=%s lt=%s pct=%s",
            collateral_usd,
            debt_usd,
            liquidation_threshold,
            price_drop_pct,
        )
        return None

    return hf


def get_stress_test(wallet_address: str) -> StressTestResult:
    """
    ウォレットのストレステストを実行し、価格 -10%/-20% 時の HF を返す。

    アカウントデータを Aave Pool から取得し、各価格シナリオで HF をシミュレーションする。
    RPC 未設定 / DUMMY モードでは dummy データを使用する（fail-open）。

    AccountData.liquidation_threshold を優先使用する。
    未設定の場合は安全側 fallback として 0.75 を使用し、ログに記録する。

    Args:
        wallet_address: 対象ウォレットアドレス

    Returns:
        StressTestResult
    """
    from .client import DummyAaveClient, Web3AaveClient  # noqa: PLC0415

    masked_wallet = _mask_address(wallet_address)

    client_type = os.getenv("AAVE_CLIENT_TYPE", "dummy")

    collateral_usd: Optional[Decimal] = None
    debt_usd: Optional[Decimal] = None
    current_hf: Optional[Decimal] = None
    liquidation_threshold: Optional[Decimal] = None

    try:
        if client_type == "web3":
            rpc_url = os.getenv("AAVE_RPC_URL", "")
            pool_address = os.getenv("AAVE_POOL_ADDRESS", "")
            if not rpc_url or not pool_address:
                logger.warning(
                    "[sentinel] AAVE_RPC_URL / AAVE_POOL_ADDRESS 未設定、DUMMY フォールバック wallet=%s",
                    masked_wallet,
                )
                client_type = "dummy"
            else:
                client = Web3AaveClient(rpc_url=rpc_url, pool_address=pool_address)
                account = client.get_account_data(wallet_address)
                collateral_usd = account.total_collateral_usd
                debt_usd = account.total_debt_usd
                current_hf = account.health_factor
                # AccountData.liquidation_threshold は RPC から取得した実値 (result[3]/10000)。
                # 取得できなかった場合（None）は安全側 fallback として 0.75 を使用する。
                liquidation_threshold = account.liquidation_threshold or Decimal("0.75")
                if account.liquidation_threshold is None:
                    logger.warning(
                        "[sentinel] liquidation_threshold 未取得、安全側 fallback 0.75 を使用 wallet=%s",
                        masked_wallet,
                    )

        if client_type != "web3":
            dummy = DummyAaveClient()
            account = dummy.get_account_data(wallet_address)
            collateral_usd = account.total_collateral_usd
            debt_usd = account.total_debt_usd
            current_hf = account.health_factor
            liquidation_threshold = account.liquidation_threshold or Decimal("0.80")

        logger.info(
            "[sentinel] account data wallet=%s collateral=%s debt=%s hf=%s lt=%s",
            masked_wallet,
            collateral_usd,
            debt_usd,
            current_hf,
            liquidation_threshold,
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[sentinel] get_account_data 失敗 wallet=%s error=%s",
            masked_wallet,
            type(exc).__name__,
        )
        return StressTestResult(
            wallet_address=wallet_address,
            current_hf=None,
            current_collateral_usd=None,
            current_debt_usd=None,
            liquidation_threshold=None,
            error=f"アカウントデータ取得失敗: {type(exc).__name__}",
        )

    # 価格シナリオ: -10%, -20%
    scenarios: list[StressTestScenario] = []
    for drop_pct in [Decimal("0.10"), Decimal("0.20")]:
        if (
            collateral_usd is not None
            and debt_usd is not None
            and liquidation_threshold is not None
        ):
            simulated_hf = simulate_hf_at_price_drop(
                collateral_usd=collateral_usd,
                debt_usd=debt_usd,
                liquidation_threshold=liquidation_threshold,
                price_drop_pct=drop_pct,
            )
            collateral_after = collateral_usd * (Decimal("1") - drop_pct)
        else:
            simulated_hf = None
            collateral_after = None

        scenarios.append(
            StressTestScenario(
                price_drop_pct=drop_pct,
                simulated_hf=simulated_hf,
                collateral_after_usd=collateral_after,
            )
        )

    return StressTestResult(
        wallet_address=wallet_address,
        current_hf=current_hf,
        current_collateral_usd=collateral_usd,
        current_debt_usd=debt_usd,
        liquidation_threshold=liquidation_threshold,
        scenarios=scenarios,
    )


# ---------------------------------------------------------------------------
# プール赤字モニター
# ---------------------------------------------------------------------------


class PoolHealthMonitor:
    """
    Aave プール赤字（getReserveDeficit）を監視し、閾値超過時に Slack アラートを送信する。

    既存 monitor.py の get_health_factor / get_aave_balance と同じレイヤーで動作する。
    安全装置として fail-open 設計（RPC 障害時は空レポートを返す）。

    NOTE: 監視対象は現在 USDC のみ（DEFAULT_DEFICIT_TOKENS 参照）。
    WETH / wstETH は Aave Price Oracle 統合後に追加する。
    """

    def __init__(
        self,
        deficit_alert_threshold: Decimal = DEFICIT_ALERT_THRESHOLD,
        tokens: Optional[list[str]] = None,
    ) -> None:
        self._threshold = deficit_alert_threshold
        self._tokens = tokens or DEFAULT_DEFICIT_TOKENS

    def check_pool_deficits(self, chain_name: str = "base") -> PoolHealthReport:
        """
        対象チェーンのプール赤字を確認し PoolHealthReport を返す。

        赤字が DEFICIT_ALERT_THRESHOLD ($10,000) を超えた場合は Slack 通知する。
        RPC 未設定または DUMMY モードでは空レポートを返す（fail-open）。

        Args:
            chain_name: 対象チェーン（chains.py CHAIN_REGISTRY のキー）

        Returns:
            PoolHealthReport
        """
        report = PoolHealthReport(chain_name=chain_name)

        client_type = os.getenv("AAVE_CLIENT_TYPE", "dummy")
        if client_type != "web3":
            logger.info(
                "[pool_health] AAVE_CLIENT_TYPE=%s、赤字チェックはスキップ（dummy モード）",
                client_type,
            )
            return report

        rpc_url = os.getenv("AAVE_RPC_URL", "")
        pool_address = os.getenv("AAVE_POOL_ADDRESS", "")

        if not rpc_url or not pool_address:
            logger.warning("[pool_health] AAVE_RPC_URL / AAVE_POOL_ADDRESS 未設定、スキップ")
            return report

        try:
            from .chains import get_chain_config  # noqa: PLC0415

            chain_config = get_chain_config(chain_name)
        except ValueError as exc:
            logger.warning("[pool_health] チェーン設定取得失敗 chain=%s error=%s", chain_name, exc)
            report.error = f"チェーン設定エラー: {exc}"
            return report

        deficits: list[PoolDeficitInfo] = []
        total_deficit = Decimal("0")
        alert_triggered = False

        for symbol in self._tokens:
            token_address = chain_config.tokens.get(symbol)
            if not token_address:
                logger.debug(
                    "[pool_health] chain=%s にトークン %s が見つからないためスキップ",
                    chain_name,
                    symbol,
                )
                continue

            deficit_usd = self._fetch_reserve_deficit(rpc_url, pool_address, token_address, symbol)
            if deficit_usd is None:
                continue

            triggered = deficit_usd > self._threshold
            deficits.append(
                PoolDeficitInfo(
                    asset_symbol=symbol,
                    deficit_usd=deficit_usd,
                    alert_triggered=triggered,
                )
            )
            total_deficit += deficit_usd
            if triggered:
                alert_triggered = True
                self._send_deficit_alert(chain_name, symbol, deficit_usd)

        report.deficits = deficits
        report.total_deficit_usd = total_deficit
        report.alert_triggered = alert_triggered
        return report

    def _fetch_reserve_deficit(
        self,
        rpc_url: str,
        pool_address: str,
        token_address: str,
        symbol: str,
    ) -> Optional[Decimal]:
        """
        Aave Pool.getReserveDeficit(asset) を呼び出して赤字 USD 相当を返す。

        getReserveDeficit() はプールの unbacked deficit をトークン単位 (wei) で返す。
        現在は USDC (6 decimals) のみを対象とし、1 USDC = 1 USD として換算する。

        WETH / wstETH (18 decimals) は Price Oracle 統合後に追加する予定。
        理由: Price Oracle なしでは 1 token = 1 USD となり、実際の USD 価値と桁違いになる。

        NOTE: getReserveDeficit() は Aave V3.1 以降で利用可能。
        古いプール実装では ABI missing エラーが出るため try-except で fail-open とする。
        """
        try:
            from web3 import Web3  # noqa: PLC0415

            w3 = Web3(Web3.HTTPProvider(rpc_url))
            checksum_pool = Web3.to_checksum_address(pool_address)
            checksum_token = Web3.to_checksum_address(token_address)

            pool_contract = w3.eth.contract(
                address=checksum_pool,
                abi=_POOL_GET_RESERVE_DEFICIT_ABI,
            )
            raw_deficit: int = pool_contract.functions.getReserveDeficit(checksum_token).call()

            # USDC = 6 decimals。他のステーブルコイン（USDbC, EURC）も 6 decimals。
            # TODO(sentinel): Aave Price Oracle 統合で WETH/wstETH の正確な USD 換算を行う
            decimals = 6 if symbol in ("USDC", "USDbC", "EURC") else 18
            deficit_usd = Decimal(raw_deficit) / Decimal(10**decimals)

            logger.info(
                "[pool_health] getReserveDeficit symbol=%s deficit=%s USD",
                symbol,
                deficit_usd,
            )
            return deficit_usd

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[pool_health] getReserveDeficit 失敗 symbol=%s error=%s",
                symbol,
                type(exc).__name__,
            )
            return None

    def _send_deficit_alert(self, chain_name: str, symbol: str, deficit_usd: Decimal) -> None:
        """
        プール赤字アラートを Slack に送信する。

        既存 SlackNotificationSender を再利用。送信失敗は fail-open（ログのみ）。
        """
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            logger.warning(
                "[pool_health] SLACK_WEBHOOK_URL 未設定、アラートをスキップ chain=%s symbol=%s",
                chain_name,
                symbol,
            )
            return

        try:
            from app.notifications.schemas import (  # noqa: PLC0415
                NotificationChannel,
                NotificationMessage,
                NotificationSeverity,
            )
            from app.notifications.slack_sender import SlackNotificationSender  # noqa: PLC0415

            sender = SlackNotificationSender(webhook_url=webhook_url)
            msg = NotificationMessage(
                channel=NotificationChannel.SLACK,
                severity=NotificationSeverity.ALERT,
                title=f"[Aave] プール赤字アラート: {symbol} on {chain_name}",
                body=(
                    f"チェーン: {chain_name}\n"
                    f"アセット: {symbol}\n"
                    f"赤字額（概算）: ${deficit_usd:.2f} USD\n"
                    f"閾値: ${self._threshold:.0f} USD"
                ),
            )
            sender.send(msg)
            logger.info(
                "[pool_health] Slack アラート送信 chain=%s symbol=%s deficit=%s",
                chain_name,
                symbol,
                deficit_usd,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[pool_health] Slack 送信エラー: %s", type(exc).__name__)


# ---------------------------------------------------------------------------
# ABI 定義（最小限）
# ---------------------------------------------------------------------------

# Aave V3.1 Pool.getReserveDeficit(address asset) → (uint256)
_POOL_GET_RESERVE_DEFICIT_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveDeficit",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _mask_address(address: str) -> str:
    """ウォレットアドレスを先頭6文字+末尾4文字にマスクする（ログ安全化）。"""
    if not address or len(address) < 10:
        return "****"
    return f"{address[:6]}...{address[-4:]}"
