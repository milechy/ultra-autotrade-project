# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance クライアント。"""

from __future__ import annotations

import logging
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.protocols.base import (
    BaseProtocolClient,
    ProtocolHealthMetrics,
    ProtocolPosition,
    TransactionResult,
)

from .config import PendleConfig
from .schemas import PendleMarketInfo

logger = logging.getLogger(__name__)


class AbstractPendleClient(BaseProtocolClient):
    """Pendle クライアントの抽象基底クラス。"""

    # --- BaseProtocolClient 実装 ---

    def get_protocol_name(self) -> str:
        """プロトコル名を返す。"""
        return "pendle"

    def get_supported_assets(self) -> list[str]:
        """サポートするアセット一覧を返す。"""
        return ["stETH", "PT", "YT", "SY"]

    async def get_current_apy(self) -> Decimal:
        """現在の implied APY を返す（デフォルトマーケット使用）。"""
        from app.protocols.pendle.config import get_pendle_config  # noqa: PLC0415

        config = get_pendle_config()
        market_info = await self.get_market_info(config.market_address)
        return market_info.implied_apy

    async def supply(self, amount: Decimal, asset: str) -> TransactionResult:
        """アセットを Pendle に預け入れる（SY ミントとして実装）。

        Args:
            amount: 預け入れ量
            asset: アセットアドレスまたは識別子

        Returns:
            TransactionResult: トランザクション結果
        """
        result = await self.mint_sy(asset, amount)
        success = bool(result.get("success", False))
        return TransactionResult(
            success=success,
            tx_hash=result.get("tx_hash"),
            amount=amount,
            error=None if success else result.get("error", "mint_sy 失敗"),
        )

    async def withdraw(self, amount: Decimal, asset: str) -> TransactionResult:
        """PT をリデームして引き出す（BaseProtocolClient インターフェース）。"""
        from app.protocols.pendle.config import get_pendle_config  # noqa: PLC0415

        config = get_pendle_config()
        result = await self.redeem_pt(amount, config.market_address)
        success = bool(result.get("success", False))
        return TransactionResult(
            success=success,
            tx_hash=result.get("tx_hash"),
            amount=amount,
            error=None if success else result.get("error", "redeem_pt 失敗"),
        )

    async def get_position(self) -> ProtocolPosition:
        """ポジション情報を返す（PoC: デフォルトマーケットの情報使用）。"""
        from app.protocols.pendle.config import get_pendle_config  # noqa: PLC0415

        config = get_pendle_config()
        try:
            market_info = await self.get_market_info(config.market_address)
            return ProtocolPosition(
                protocol_name=self.get_protocol_name(),
                asset="PT",
                balance=Decimal("0"),
                value_usd=market_info.tvl_usd,
            )
        except Exception:
            return ProtocolPosition(
                protocol_name=self.get_protocol_name(),
                asset="PT",
                balance=Decimal("0"),
                value_usd=Decimal("0"),
            )

    async def get_health_metrics(self) -> ProtocolHealthMetrics:
        """ヘルスメトリクスを返す。"""
        from app.protocols.pendle.config import get_pendle_config  # noqa: PLC0415

        config = get_pendle_config()
        try:
            market_info = await self.get_market_info(config.market_address)
            implied_apy = market_info.implied_apy
            tvl = market_info.tvl_usd
            is_healthy = tvl >= Decimal("1000000") and implied_apy <= Decimal("100")
            # リスクスコア: TVL 不足 or APY 異常で上昇
            risk_score = Decimal("0")
            if tvl < Decimal("1000000"):
                risk_score += Decimal("0.5")
            if implied_apy > Decimal("100"):
                risk_score += Decimal("0.5")
            elif implied_apy > Decimal("50"):
                risk_score += Decimal("0.2")
            risk_score = min(risk_score, Decimal("1"))
            return ProtocolHealthMetrics(
                protocol_name=self.get_protocol_name(),
                is_healthy=is_healthy,
                risk_score=risk_score,
                details={
                    "implied_apy": str(implied_apy),
                    "tvl_usd": str(tvl),
                    "days_to_maturity": str(market_info.days_to_maturity),
                },
            )
        except Exception as exc:
            return ProtocolHealthMetrics(
                protocol_name=self.get_protocol_name(),
                is_healthy=False,
                risk_score=Decimal("1"),
                details={"error": str(exc)},
            )

    # --- Pendle 固有の抽象メソッド ---

    @abstractmethod
    async def mint_sy(self, token_address: str, amount: Decimal) -> dict[str, Any]:
        """yield-bearing アセットを SY にラップする。"""
        ...

    @abstractmethod
    async def mint_pt_yt(self, sy_amount: Decimal, market_address: str) -> dict[str, Any]:
        """SY を PT と YT に分割する。"""
        ...

    @abstractmethod
    async def redeem_pt(self, pt_amount: Decimal, market_address: str) -> dict[str, Any]:
        """満期時に PT をリデームする。"""
        ...

    @abstractmethod
    async def redeem_yt(self, yt_amount: Decimal, market_address: str) -> dict[str, Any]:
        """YT をリデームする。"""
        ...

    @abstractmethod
    async def get_market_info(self, market_address: str) -> PendleMarketInfo:
        """マーケット情報を取得する。"""
        ...

    @abstractmethod
    async def get_pt_price(self, market_address: str) -> Decimal:
        """PT 価格（ディスカウント）を取得する。"""
        ...

    @abstractmethod
    async def get_yt_price(self, market_address: str) -> Decimal:
        """YT 価格を取得する。"""
        ...


class DummyPendleClient(AbstractPendleClient):
    """テスト・サンドボックス用 Pendle スタブクライアント。"""

    # ダミー定数
    _PT_PRICE = Decimal("0.95")  # 5% ディスカウント
    _YT_PRICE = Decimal("0.05")
    _MATURITY_DAYS = 30
    _IMPLIED_APY = Decimal("5.2")
    _TVL_USD = Decimal("50000000")

    def __init__(self, config: PendleConfig) -> None:
        self._config = config
        logger.info("DummyPendleClient initialized（sandbox モード）")

    def _dummy_maturity(self) -> datetime:
        """現在時刻から 30 日後の満期日時を返す。"""
        return datetime.now(tz=timezone.utc) + timedelta(days=self._MATURITY_DAYS)

    async def mint_sy(self, token_address: str, amount: Decimal) -> dict[str, Any]:
        """yield-bearing アセット → SY ラップのシミュレーション。"""
        logger.info(
            "DummyPendleClient.mint_sy: token=%s, amount=%s（シミュレーション）",
            token_address[:10] if len(token_address) > 10 else token_address,
            amount,
        )
        return {
            "success": True,
            "sy_received": amount,
            "tx_hash": "0x" + "aa" * 32,
        }

    async def mint_pt_yt(self, sy_amount: Decimal, market_address: str) -> dict[str, Any]:
        """SY → PT + YT 分割のシミュレーション。"""
        logger.info(
            "DummyPendleClient.mint_pt_yt: sy_amount=%s, market=%s（シミュレーション）",
            sy_amount,
            market_address[:10] if len(market_address) > 10 else market_address,
        )
        pt_amount = sy_amount / self._PT_PRICE
        yt_amount = sy_amount / self._YT_PRICE
        return {
            "success": True,
            "pt_received": pt_amount,
            "yt_received": yt_amount,
            "tx_hash": "0x" + "bb" * 32,
        }

    async def redeem_pt(self, pt_amount: Decimal, market_address: str) -> dict[str, Any]:
        """PT リデームのシミュレーション（満期時 1:1 交換）。"""
        logger.info("DummyPendleClient.redeem_pt: pt_amount=%s（シミュレーション）", pt_amount)
        return {
            "success": True,
            "underlying_received": pt_amount,
            "tx_hash": "0x" + "cc" * 32,
        }

    async def redeem_yt(self, yt_amount: Decimal, market_address: str) -> dict[str, Any]:
        """YT リデームのシミュレーション。"""
        logger.info("DummyPendleClient.redeem_yt: yt_amount=%s（シミュレーション）", yt_amount)
        underlying = yt_amount * self._YT_PRICE
        return {
            "success": True,
            "underlying_received": underlying,
            "tx_hash": "0x" + "dd" * 32,
        }

    async def get_market_info(self, market_address: str) -> PendleMarketInfo:
        """ダミーマーケット情報を返す。"""
        maturity = self._dummy_maturity()
        return PendleMarketInfo(
            market_address=market_address,
            underlying_asset="stETH",
            maturity=maturity,
            days_to_maturity=self._MATURITY_DAYS,
            implied_apy=self._IMPLIED_APY,
            pt_price=self._PT_PRICE,
            yt_price=self._YT_PRICE,
            tvl_usd=self._TVL_USD,
        )

    async def get_pt_price(self, market_address: str) -> Decimal:
        """PT 価格（0.95 = 5% ディスカウント）を返すスタブ。"""
        return self._PT_PRICE

    async def get_yt_price(self, market_address: str) -> Decimal:
        """YT 価格（0.05）を返すスタブ。"""
        return self._YT_PRICE


class PendleWebClient(AbstractPendleClient):
    """Pendle Finance 本番 REST API クライアント（読み取り専用）。

    Pendle V2 API（api-v2.pendle.finance）からマーケット情報・APY・PT/YT価格を取得する。
    オンチェーン操作（mint/redeem）は Phase 3 以降に対応。
    API 接続失敗時はフォールバック値を返し、500 を発生させない（fail-open 設計）。
    """

    _API_BASE = "https://api-v2.pendle.finance/core/v1"
    _CHAIN_ID_MAP: dict[str, str] = {
        "arbitrum": "42161",
        "ethereum": "1",
        "polygon": "137",
        "sepolia": "421614",  # Arbitrum Sepolia
    }
    _REQUEST_TIMEOUT = 10.0

    def __init__(self, config: PendleConfig) -> None:
        self._config = config
        self._chain_id = self._CHAIN_ID_MAP.get(config.chain, "42161")
        logger.info(
            "PendleWebClient initialized (chain=%s, chain_id=%s)",
            config.chain,
            self._chain_id,
        )

    async def _fetch_market_data(self, market_address: str) -> dict[str, Any]:
        """Pendle API からマーケットデータを取得する。"""
        url = f"{self._API_BASE}/{self._chain_id}/markets/{market_address}"
        async with httpx.AsyncClient(timeout=self._REQUEST_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    async def get_market_info(self, market_address: str) -> PendleMarketInfo:
        """Pendle API からマーケット情報を取得する。API 失敗時はフォールバック値を返す。"""
        try:
            data = await self._fetch_market_data(market_address)

            # 満期日時（UNIX タイムスタンプ）
            expiry_ts = int(data.get("expiry", 0))
            maturity = datetime.fromtimestamp(expiry_ts, tz=timezone.utc)
            days_to_maturity = max(0, (maturity - datetime.now(tz=timezone.utc)).days)

            # implied APY は小数形式（0.052 = 5.2%）→ % 変換
            implied_apy_raw = data.get("impliedApy", 0)
            implied_apy = Decimal(str(implied_apy_raw)) * Decimal("100")

            # PT/YT 価格
            pt_price = Decimal(str(data.get("pt", {}).get("price", {}).get("usd", "0.95")))
            yt_price = Decimal(str(data.get("yt", {}).get("price", {}).get("usd", "0.05")))

            # TVL（USD）
            tvl_usd = Decimal(str(data.get("liquidity", {}).get("usd", "0")))

            # 原資産シンボル
            underlying = data.get("underlyingAsset", {}).get("symbol", "stETH")

            return PendleMarketInfo(
                market_address=market_address,
                underlying_asset=underlying,
                maturity=maturity,
                days_to_maturity=days_to_maturity,
                implied_apy=implied_apy,
                pt_price=pt_price,
                yt_price=yt_price,
                tvl_usd=tvl_usd,
            )
        except Exception as exc:
            logger.warning("get_market_info API 失敗、フォールバック値を使用: %s", exc)
            maturity = datetime.now(tz=timezone.utc) + timedelta(days=30)
            return PendleMarketInfo(
                market_address=market_address,
                underlying_asset="stETH",
                maturity=maturity,
                days_to_maturity=30,
                implied_apy=Decimal("5.2"),
                pt_price=Decimal("0.95"),
                yt_price=Decimal("0.05"),
                tvl_usd=Decimal("0"),
            )

    async def get_pt_price(self, market_address: str) -> Decimal:
        """PT 価格を取得する。"""
        info = await self.get_market_info(market_address)
        return info.pt_price

    async def get_yt_price(self, market_address: str) -> Decimal:
        """YT 価格を取得する。"""
        info = await self.get_market_info(market_address)
        return info.yt_price

    async def mint_sy(self, token_address: str, amount: Decimal) -> dict[str, Any]:
        """SY ミント（Phase 2 PoC: オンチェーン操作は未実装）。"""
        logger.warning("PendleWebClient.mint_sy: Phase 2 PoC のためオンチェーン操作を拒否")
        return {"success": False, "error": "オンチェーン操作は Phase 3 以降に対応予定です"}

    async def mint_pt_yt(self, sy_amount: Decimal, market_address: str) -> dict[str, Any]:
        """PT/YT ミント（Phase 2 PoC: オンチェーン操作は未実装）。"""
        logger.warning("PendleWebClient.mint_pt_yt: Phase 2 PoC のためオンチェーン操作を拒否")
        return {"success": False, "error": "オンチェーン操作は Phase 3 以降に対応予定です"}

    async def redeem_pt(self, pt_amount: Decimal, market_address: str) -> dict[str, Any]:
        """PT リデーム（Phase 2 PoC: オンチェーン操作は未実装）。"""
        logger.warning("PendleWebClient.redeem_pt: Phase 2 PoC のためオンチェーン操作を拒否")
        return {"success": False, "error": "オンチェーン操作は Phase 3 以降に対応予定です"}

    async def redeem_yt(self, yt_amount: Decimal, market_address: str) -> dict[str, Any]:
        """YT リデーム（Phase 2 PoC: オンチェーン操作は未実装）。"""
        logger.warning("PendleWebClient.redeem_yt: Phase 2 PoC のためオンチェーン操作を拒否")
        return {"success": False, "error": "オンチェーン操作は Phase 3 以降に対応予定です"}


def get_pendle_client(config: PendleConfig) -> AbstractPendleClient:
    """設定に基づいて適切な PendleClient を返す。"""
    import os  # noqa: PLC0415

    app_env = os.getenv("APP_ENV", "development")
    if app_env in ("staging", "production") and config.sandbox:
        logger.error("DummyClient is forbidden in %s environment", app_env)
        raise RuntimeError(f"DummyClient cannot be used in {app_env} environment")
    if config.sandbox:
        logger.warning("Using DummyClient — not for production")
        return DummyPendleClient(config)
    logger.info("Using PendleWebClient (Pendle REST API)")
    return PendleWebClient(config)
