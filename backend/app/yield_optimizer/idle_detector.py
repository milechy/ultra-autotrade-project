# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/yield_optimizer/idle_detector.py
"""
アイドル資本検出器。

Bybit の USDC 空き残高 - Morpho 運用中金額 = アイドル USDC を計算し、
Morpho デプロイ推奨可否を判定する。

アイドル判定ロジック:
  1. Bybit の fetch_balance() から USDC の free 残高を取得
  2. Morpho ポジション合計 (deposited_amount) を差し引く
  3. アイドル額 >= IDLE_THRESHOLD かつ Bybit のオープンポジションが存在しない → True

金融計算: Decimal のみ (float 禁止)。
外部 API 失敗時は fail-open (デプロイ不推奨として False を返す)。

NOTE (フラグ): Bybit の残高取得は BybitSandboxClient.fetch_balance() を再利用。
  戻り値の構造: {"USDC": {"free": ..., "used": ..., "total": ...}, ...}
  USDC キーが存在しない場合 (USDT のみなど) は Decimal("0") とみなす。
  本番環境で USDC 残高が取得できない場合はこのフラグを参照して確認すること。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Optional

from .schemas import IdleCapitalReport

if TYPE_CHECKING:
    pass  # pragma: no cover

logger = logging.getLogger(__name__)

# デプロイ閾値: アイドル USDC がこの金額以上の場合のみ Morpho 入金を推奨
IDLE_THRESHOLD = Decimal("100.00")


def _decimal_free_usdc(balance: dict[str, Any]) -> Decimal:
    """
    ccxt fetch_balance() の戻り値から USDC の free 残高を Decimal で取得する。

    Args:
        balance: BybitSandboxClient.fetch_balance() の戻り値

    Returns:
        USDC free 残高 (Decimal)。キーが存在しない場合は Decimal("0")。
    """
    usdc_entry = balance.get("USDC") or balance.get("usdc")
    if usdc_entry is None:
        return Decimal("0")
    try:
        return Decimal(str(usdc_entry.get("free") or "0"))
    except (InvalidOperation, TypeError, AttributeError):
        return Decimal("0")


def _decimal_from_str(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """文字列 / 数値を安全に Decimal 変換する。"""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


class IdleCapitalDetector:
    """
    Bybit USDC 残高と Morpho 運用中金額を比較してアイドル資本を検出する。

    Args:
        exchange_client: BybitSandboxClient インスタンス (None の場合は fail-open)
        morpho_client: MorphoClient インスタンス (None の場合は運用中 0 とみなす)
        idle_threshold: デプロイ推奨の最低アイドル額 (Decimal)
    """

    def __init__(
        self,
        exchange_client: Optional[Any] = None,
        morpho_client: Optional[Any] = None,
        idle_threshold: Decimal = IDLE_THRESHOLD,
    ) -> None:
        self._exchange_client = exchange_client
        self._morpho_client = morpho_client
        self._idle_threshold = idle_threshold

    def get_bybit_free_usdc(self) -> Decimal:
        """
        Bybit から USDC の空き残高を取得する。

        Returns:
            USDC free 残高 (Decimal)。取得失敗時は Decimal("0") (fail-open)。
        """
        if self._exchange_client is None:
            logger.warning("get_bybit_free_usdc: no exchange_client, returning 0 (fail-open)")
            return Decimal("0")

        try:
            balance = self._exchange_client.fetch_balance()
            return _decimal_free_usdc(balance)
        except Exception as exc:
            logger.warning("get_bybit_free_usdc: fetch_balance failed (fail-open): %s", exc)
            return Decimal("0")

    def get_deployed_amount(self) -> Decimal:
        """
        Morpho Vault に運用中の USDC 合計を取得する。

        Returns:
            運用中 USDC 合計 (Decimal)。取得失敗時は Decimal("0") (fail-open)。
        """
        if self._morpho_client is None:
            return Decimal("0")

        try:
            positions = self._morpho_client.get_all_positions()
            total = Decimal("0")
            for pos in positions:
                total += _decimal_from_str(pos.deposited_amount)
            return total
        except Exception as exc:
            logger.warning("get_deployed_amount: morpho API error (fail-open): %s", exc)
            return Decimal("0")

    def _has_open_bybit_positions(self) -> bool:
        """
        Bybit にオープンポジションが存在するかを簡易判定する。

        fetch_balance() の 'used' 残高が 0 超かどうかで判定する。
        取得失敗時は True を返す (安全側に倒す)。

        Returns:
            True = ポジションあり / False = ポジションなし
        """
        if self._exchange_client is None:
            return True  # 保守的判定

        try:
            balance = self._exchange_client.fetch_balance()
            # USDC の used 残高 > 0 をポジションありとみなす
            usdc_entry = balance.get("USDC") or balance.get("usdc") or {}
            used = _decimal_from_str(usdc_entry.get("used") or "0")
            return used > Decimal("0")
        except Exception as exc:
            logger.warning(
                "_has_open_bybit_positions: fetch_balance failed, assuming positions exist: %s",
                exc,
            )
            return True

    def get_idle_capital(self) -> Decimal:
        """
        アイドル USDC 残高を返す。

        アイドル = Bybit USDC free - Morpho 運用中金額。
        負になった場合は Decimal("0") を返す。

        Returns:
            アイドル USDC (Decimal、0 以上)
        """
        bybit_free = self.get_bybit_free_usdc()
        deployed = self.get_deployed_amount()
        idle = bybit_free - deployed
        return max(Decimal("0"), idle)

    def should_deploy_to_morpho(self) -> bool:
        """
        Morpho へのデプロイを推奨するかを判定する。

        条件:
          1. アイドル USDC >= IDLE_THRESHOLD (デフォルト $100)
          2. Bybit にオープンポジションが存在しない

        Returns:
            True = デプロイ推奨 / False = 推奨しない
        """
        idle = self.get_idle_capital()
        if idle < self._idle_threshold:
            logger.debug(
                "should_deploy_to_morpho: idle=%.2f < threshold=%.2f → False",
                idle,
                self._idle_threshold,
            )
            return False

        if self._has_open_bybit_positions():
            logger.debug("should_deploy_to_morpho: open Bybit positions exist → False")
            return False

        logger.info(
            "should_deploy_to_morpho: idle=%.2f >= threshold=%.2f, no open positions → True",
            idle,
            self._idle_threshold,
        )
        return True

    def build_report(self) -> IdleCapitalReport:
        """
        アイドル資本レポートを生成する。

        Returns:
            IdleCapitalReport
        """
        bybit_free = self.get_bybit_free_usdc()
        deployed = self.get_deployed_amount()
        idle = max(Decimal("0"), bybit_free - deployed)
        has_positions = self._has_open_bybit_positions()

        should_deploy = idle >= self._idle_threshold and not has_positions

        reason: Optional[str] = None
        if not should_deploy:
            if idle < self._idle_threshold:
                reason = f"アイドル残高 ${idle:.2f} が閾値 ${self._idle_threshold:.2f} 未満"
            elif has_positions:
                reason = "Bybit にオープンポジションが存在するため見送り"

        return IdleCapitalReport(
            bybit_free_usdc=str(bybit_free),
            deployed_amount=str(deployed),
            idle_amount=str(idle),
            should_deploy=should_deploy,
            threshold=str(self._idle_threshold),
            reason=reason,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )


def get_idle_threshold() -> Decimal:
    """
    ENV IDLE_CAPITAL_THRESHOLD_USD から閾値を取得する。

    デフォルト: $100.00
    """
    raw = os.getenv("IDLE_CAPITAL_THRESHOLD_USD", "100.00")
    try:
        v = Decimal(raw)
        if v <= Decimal("0"):
            return IDLE_THRESHOLD
        return v
    except (InvalidOperation, ValueError):
        logger.warning(
            "get_idle_threshold: invalid IDLE_CAPITAL_THRESHOLD_USD=%r, using default", raw
        )
        return IDLE_THRESHOLD
