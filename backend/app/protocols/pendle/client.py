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

from .cache import PendleMarketCache
from .config import PendleConfig
from .schemas import (
    PendleMarketInfo,
    RouterV4AddLiquidityRequest,
    RouterV4AddLiquidityResult,
    RouterV4Approval,
    RouterV4SwapRequest,
    RouterV4SwapResult,
)

logger = logging.getLogger(__name__)


class PendleBuildTxError(Exception):
    """パートナー署名用の未署名 tx 構築に失敗したことを表す。

    Router 照合不一致 / calldata 欠損 / SDK HTTP 失敗など、未署名 tx を安全に組めない
    状況で送出する（fail-closed: 不確実なら未署名 tx を返さない）。
    """


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
    # **base を必ず含めること**: 2026-07-17 まで base が無く、`PENDLE_CHAIN=base` でも
    # 42161(Arbitrum) に既定化 → market data が 404 → except 節のフォールバック
    # （stETH / tvl=0 / APY 5.2% の**架空値**）が返っていた。tvl=0 は流動性ガードが
    # 全 block する値なので、Phase-D の Pendle は「静かに常時 block」状態だった。
    # D2 で PendleRouterV4Client 側だけ base を追加し、本クラスが漏れていた。
    _CHAIN_ID_MAP: dict[str, str] = {
        "arbitrum": "42161",
        "ethereum": "1",
        "polygon": "137",
        "sepolia": "421614",  # Arbitrum Sepolia（Pendle 未対応 = 404）
        "base": "8453",  # [Phase D] Base Mainnet (yoUSD stablecoin PT)
        "base_sepolia": "84532",  # Base Sepolia（Pendle 未対応 = 404）
    }
    _REQUEST_TIMEOUT = 10.0

    def __init__(self, config: PendleConfig) -> None:
        self._config = config
        chain_id = self._CHAIN_ID_MAP.get(config.chain)
        if chain_id is None:
            # 黙って別チェーンに既定化すると「404 → 架空のフォールバック値」で気づけない。
            # 明示的に警告して、設定ミスを観測可能にする。
            logger.warning(
                "PendleWebClient: 未知の chain=%r。%s に既定化する（market data は 404 になり "
                "フォールバック値が返るため、PENDLE_CHAIN を確認すること）",
                config.chain,
                "42161",
            )
            chain_id = "42161"
        self._chain_id = chain_id
        logger.info(
            "PendleWebClient initialized (chain=%s, chain_id=%s)",
            config.chain,
            self._chain_id,
        )

    @staticmethod
    def _parse_expiry(raw: Any) -> datetime:
        """``expiry`` を datetime にする。

        実 API は ISO8601 文字列（``"2026-09-24T00:00:00.000Z"``）を返すが、UNIX 秒（int/数字文字列）
        で返る経路も想定して両対応にする。解釈できない値は ValueError を送出し、呼び出し側の
        フォールバック（＝tvl=0 で流動性ガードが block）に落とす（fail-closed 側に倒す）。
        """
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        if isinstance(raw, str) and raw.strip():
            value = raw.strip()
            if value.isdigit():
                return datetime.fromtimestamp(int(value), tz=timezone.utc)
            # "...Z" は Python 3.10 以前の fromisoformat が解釈できないため +00:00 に正規化する。
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError(f"expiry を解釈できません: {raw!r}")

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

            # 満期日時。実 API は **ISO8601 文字列**（"2026-09-24T00:00:00.000Z"）を返す。
            # 旧実装は int() で UNIX 秒として解釈しており必ず ValueError → except 節の
            # フォールバック（tvl=0）に落ちていた＝流動性ガードが常に block していた。
            maturity = self._parse_expiry(data.get("expiry"))
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


class PendleRouterV4Client:
    """Pendle RouterV4 クライアント（YT/PT 売買 + add_liquidity）。

    Pendle Hosted SDK の **Convert API**（``/core/v2/sdk/{chainId}/convert``）で calldata を生成する。

    **2026-07-17 修正**: 旧実装は ``https://api-v2.pendle.finance/sdk/api/v1/{chain}/swapExactTokenForPt``
    を叩いていたが、この経路は**実在しない**（全チェーンで 404 "fault filter abort"、実 API で確認）。
    Pendle は個別エンドポイント（/swap 等）を廃止し Convert API に統合済み。旧実装は URL・パラメータ名・
    レスポンス形の全てが実物と食い違っており、動かせば必ず 404 で fail-closed に落ちていた
    （全経路 dormant + テストが HTTP をモックしていたため未検出。本番影響はゼロ）。

    フェーズ境界（誤送信防止）:
    - **本クラスは calldata 取得まで**。tx 送信・署名・web3 import は一切行わない（tx_hash は常に None）。
    - 実 broadcast は委譲 SCW 経路（`app/proposals/pendle_scw.py` → `scw_executor`）が二段ガード
      （`PENDLE_ENABLE_ONCHAIN_WRITE` + `_should_use_scw_route`）の下でのみ行う。

    設計方針:
    - calldata は SDK が生成するため、こちらでの ABI encode は不要。
    - **`routes[0].tx.to` は必ず Router アドレスと照合する**（改竄・誘導された任意コントラクト宛
      calldata を拒否）。Convert API は approve の spender を返さないため、照合済みの Router を
      spender として補完する（`_extract_approvals` 参照）。
    - 金額は必ず Decimal 型。float 使用禁止。token decimals を解決して桁ズレを防ぐ。
    - 秘密鍵は config 経由で環境変数から取得。ログに出力しない。
    - 外部 HTTP 失敗・照合不一致は例外を握りつぶさず RouterV4SwapResult(success=False) を返す
      （fail-closed: 不確実なら成功扱いにしない）。
    - slippage デフォルト 0.5%（Decimal("0.005")）。
    """

    #: Convert API のベース。個別エンドポイント（swapExactTokenForPt 等）は廃止済み。
    _SDK_BASE = "https://api-v2.pendle.finance/core"
    _DEFAULT_SLIPPAGE = Decimal("0.005")
    _REQUEST_TIMEOUT: float = 15.0

    #: **YT 売買 (`buy_yt` / `sell_yt`) は実 API では成立しない**（既知・未対応）。
    #: Convert API は tokensIn/tokensOut に実トークンアドレスを要求するが、これらは旧 SDK 規約の
    #: リテラル "YT" を渡しており、YT アドレスの設定項目も無い。呼んでも API が 400 を返して
    #: `success=False` になる（fail-closed で害は無い）。本製品は Phase-D で **PT 専用**
    #: （`RISK_MODE_PROTOCOLS` の aggressive は stablecoin PT のみ）のため未修正のまま残す。
    #: YT を扱うなら PT と同様に `PENDLE_YT_TOKEN_ADDRESS` / decimals の追加が要る。
    #: aggregator を有効にするか。**SELL_PT(PT→USDC) には必須**（false だと
    #: "tokenOut must be in the SY token out list" で 400。yoUSD→USDC の変換に aggregator が要る）。
    #: BUY_PT では on/off で結果が変わらず、いずれの場合も `tx.to` は RouterV4 のまま
    #: （aggregator は Router 内部で呼ばれる）＝宛先 allowlist の fail-closed 性は保たれる。
    #: 実 API で両方向・両設定を確認済み（2026-07-17）。
    _ENABLE_AGGREGATOR = "true"

    # チェーン ID マッピング（Pendle SDK が使用するチェーン ID）。
    # **Pendle API は mainnet のみ対応**（1, 56, 143, 999, 8453, 9745, 42161, 10, 146, 5000, 80094）。
    # testnet は 400 "Unsupported chain id" で拒否されるため、testnet 上での検証経路は存在しない
    # （実 API で確認済み 2026-07-17）。sepolia / base_sepolia を残すのは設定ミスを
    # 「動くように見えて実は 400」ではなく明示的な失敗として観測するため。
    _CHAIN_ID_MAP: dict[str, int] = {
        "arbitrum": 42161,
        "ethereum": 1,
        "polygon": 137,
        "sepolia": 421614,  # Arbitrum Sepolia（Pendle 未対応 = 400）
        "base": 8453,  # [Phase D] Base Mainnet (yoUSD stablecoin PT)
        "base_sepolia": 84532,  # Base Sepolia（Pendle 未対応 = 400）
    }

    def __init__(
        self,
        config: PendleConfig,
        market_cache: PendleMarketCache | None = None,
    ) -> None:
        self._config = config
        self._chain_id = self._CHAIN_ID_MAP.get(config.chain, 42161)
        # market address キャッシュ（外部注入可能 / テスト容易性のため）
        # config を注入し、満期フィルタ（min_days_to_maturity）を有効化する
        self._market_cache = market_cache or PendleMarketCache(
            chain_id=self._chain_id, config=config
        )
        logger.info(
            "PendleRouterV4Client initialized (chain=%s, chain_id=%d, router=%s)",
            config.chain,
            self._chain_id,
            self._config.router_address[:10] + "...",
        )

    async def _call_sdk(self, params: dict[str, Any]) -> dict[str, Any]:
        """Pendle Convert API を呼び出して calldata を取得する。

        swap / mint / redeem は Convert API に統合されており、動作は tokensIn/tokensOut の
        組み合わせから API 側が決める（旧 SDK の endpoint 名は不要）。

        Args:
            params: クエリパラメータ（tokensIn / tokensOut / amountsIn / receiver / slippage 等）

        Returns:
            Convert API レスポンス dict

        Raises:
            httpx.HTTPError: HTTP エラー
            Exception: その他のエラー
        """
        url = f"{self._SDK_BASE}/v2/sdk/{self._chain_id}/convert"
        async with httpx.AsyncClient(timeout=self._REQUEST_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    @staticmethod
    def _first_route(sdk_response: dict[str, Any]) -> dict[str, Any]:
        """Convert API レスポンスの最初の route を返す（無ければ空 dict）。"""
        routes = sdk_response.get("routes") or []
        if routes and isinstance(routes[0], dict):
            return routes[0]
        return {}

    def _amount_to_wei(self, amount: Decimal, decimals: int = 18) -> int:
        """Decimal 量を wei 単位の int に変換する。"""
        factor = Decimal(10) ** decimals
        return int(amount * factor)

    def _wei_to_decimal(self, wei: int, decimals: int = 18) -> Decimal:
        """wei 単位の int を Decimal 量に変換する。"""
        factor = Decimal(10) ** decimals
        return Decimal(str(wei)) / factor

    def _check_guards(
        self,
        amount_in_usd: Decimal | None,
        portfolio_value_usd: Decimal | None = None,
    ) -> RouterV4SwapResult | None:
        """二段ガード + 10%上限チェック（USD 換算統一）。

        Args:
            amount_in_usd: トレード金額（USD）。portfolio_value_usd 指定時は必須（fail-closed）。
            portfolio_value_usd: ポートフォリオ総額（USD）。None のときチェックをスキップ。

        問題があれば RouterV4SwapResult(success=False) を返す。問題なければ None を返す。
        """
        # Q1 一段目: オンチェーン書き込み無効ガード
        if not self._config.enable_onchain_write:
            return RouterV4SwapResult(
                success=False,
                error="on-chain write disabled (PENDLE_ENABLE_ONCHAIN_WRITE=false)",
            )
        # Q2: 単一トレード上限（10%）チェック（USD 換算で比較）
        if portfolio_value_usd is not None:
            if amount_in_usd is None:
                return RouterV4SwapResult(
                    success=False,
                    error="amount_in_usd 未指定のため 10%上限を検証できません (fail-closed)",
                )
            limit = portfolio_value_usd * self._config.max_single_trade_pct
            if amount_in_usd > limit:
                return RouterV4SwapResult(
                    success=False,
                    error=(
                        f"exceeds max single trade ({self._config.max_single_trade_pct * 100:.0f}%): "
                        f"amount_in_usd={amount_in_usd}, limit={limit}"
                    ),
                )
        else:
            logger.warning(
                "PendleRouterV4Client: portfolio_value_usd が未指定のため 10%上限チェックをスキップ"
            )
        return None

    def _check_guards_liq(
        self,
        amount_in_usd: Decimal | None,
        portfolio_value_usd: Decimal | None = None,
    ) -> RouterV4AddLiquidityResult | None:
        """二段ガード + 10%上限チェック（add_liquidity 用、USD 換算統一）。

        Args:
            amount_in_usd: トレード金額（USD）。portfolio_value_usd 指定時は必須（fail-closed）。
            portfolio_value_usd: ポートフォリオ総額（USD）。None のときチェックをスキップ。

        問題があれば RouterV4AddLiquidityResult(success=False) を返す。問題なければ None を返す。
        """
        if not self._config.enable_onchain_write:
            return RouterV4AddLiquidityResult(
                success=False,
                error="on-chain write disabled (PENDLE_ENABLE_ONCHAIN_WRITE=false)",
            )
        if portfolio_value_usd is not None:
            if amount_in_usd is None:
                return RouterV4AddLiquidityResult(
                    success=False,
                    error="amount_in_usd 未指定のため 10%上限を検証できません (fail-closed)",
                )
            limit = portfolio_value_usd * self._config.max_single_trade_pct
            if amount_in_usd > limit:
                return RouterV4AddLiquidityResult(
                    success=False,
                    error=(
                        f"exceeds max single trade ({self._config.max_single_trade_pct * 100:.0f}%): "
                        f"amount_in_usd={amount_in_usd}, limit={limit}"
                    ),
                )
        else:
            logger.warning(
                "PendleRouterV4Client: portfolio_value_usd が未指定のため 10%上限チェックをスキップ"
            )
        return None

    def _resolve_decimals(self, token: str, explicit: int | None) -> int:
        """token の decimals を解決する。

        明示指定があればそれを優先。無ければ config の token→decimals マップで解決し、
        未知トークンは 18。非18桁トークン（USDC/USDT=6, WBTC=8）の桁ズレ事故を防ぐ。
        """
        if explicit is not None:
            return explicit
        return self._config.token_decimals(token)

    @staticmethod
    def _addr_eq(a: str | None, b: str | None) -> bool:
        """アドレスを大文字小文字無視で比較する（None/空文字は不一致扱い）。"""
        if not a or not b:
            return False
        return a.lower() == b.lower()

    def _extract_approvals(
        self, sdk_response: dict[str, Any], spender: str
    ) -> list[RouterV4Approval]:
        """Convert API の ``requiredApprovals`` を取り出す（無ければ空）。

        **Convert API は spender を返さない**（``{token, amount}`` のみ）。approve 先は常に
        route の ``tx.to``＝Router なので、呼び出し側が `_verify_router` で Router と照合済みの
        宛先を ``spender`` として渡すこと。これにより「照合済み Router 以外へは絶対に approve
        しない」という不変条件を、API の返り値に依存せずこちら側で保証する。
        """
        raw = sdk_response.get("requiredApprovals") or []
        approvals: list[RouterV4Approval] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            approvals.append(
                RouterV4Approval(
                    token=item.get("token"),
                    spender=spender,
                    amount=(str(item["amount"]) if item.get("amount") is not None else None),
                )
            )
        return approvals

    def _verify_router(self, sdk_response: dict[str, Any]) -> tuple[bool, str | None, str]:
        """Convert API の ``routes[0].tx.to`` を Router アドレスと照合する。

        aggregator 有効時も Router が内部で aggregator を呼ぶ形になり ``tx.to`` は Router のまま
        （実 API で両方向確認済み）。よって「宛先が Router であること」だけを fail-closed 条件に
        できる。approve の spender は本メソッドで照合した宛先を `_extract_approvals` に渡して補完する。

        Returns:
            (ok, to_address, error): ok=False のとき error に理由を格納する。
        """
        to_addr = self._first_route(sdk_response).get("tx", {}).get("to")
        if not self._addr_eq(to_addr, self._config.router_address):
            return False, None, "router address mismatch"
        return True, to_addr, ""

    def _extract_amount_out(
        self, sdk_response: dict[str, Any], token_out: str, decimals: int
    ) -> Decimal:
        """Convert API の ``routes[0].outputs`` から token_out の受取量を取り出す。

        outputs は複数返り得るため token_out に一致するものを優先し、無ければ先頭を使う。
        """
        outputs = self._first_route(sdk_response).get("outputs") or []
        chosen: dict[str, Any] | None = None
        for item in outputs:
            if isinstance(item, dict) and self._addr_eq(item.get("token"), token_out):
                chosen = item
                break
        if chosen is None and outputs and isinstance(outputs[0], dict):
            chosen = outputs[0]
        if not chosen or chosen.get("amount") is None:
            return Decimal("0")
        return self._wei_to_decimal(int(str(chosen["amount"])), decimals=decimals)

    async def resolve_market_address(self, underlying_asset: str) -> str | None:
        """underlying_asset シンボルから market address を動的解決する。

        キャッシュヒット時はキャッシュを返す。
        キャッシュミス時は Pendle /markets エンドポイントを呼び出す。
        API 失敗時は None を返す（fail-open 設計）。

        Args:
            underlying_asset: 原資産シンボル（例: "stETH", "wstETH"）

        Returns:
            market address 文字列、または None（失敗時 / 見つからない時）
        """
        return await self._market_cache.get_market_address(underlying_asset)

    def get_market_cache(self) -> PendleMarketCache:
        """market address キャッシュインスタンスを返す（メトリクス参照用）。"""
        return self._market_cache

    async def buy_yt(
        self,
        market_address: str,
        token_in: str,
        amount_in: Decimal,
        receiver: str,
        slippage: Decimal | None = None,
        dry_run: bool = True,
        portfolio_value_usd: Decimal | None = None,
        token_in_decimals: int | None = None,
        amount_in_usd: Decimal | None = None,
    ) -> RouterV4SwapResult:
        """YT を購入する（token_in → YT swap）。

        Args:
            market_address: 対象マーケットアドレス
            token_in: 入力トークンアドレス
            amount_in: 入力量（Decimal）
            receiver: YT 受取アドレス
            slippage: スリッページ（デフォルト 0.5% = 0.005）
            dry_run: True の場合 calldata 生成のみで tx 送信なし（デフォルト True）
            portfolio_value_usd: ポートフォリオ総額（10%上限チェック用。None でスキップ）
            token_in_decimals: 入力トークンの decimals。**非18桁トークン（USDC/USDT=6,
                WBTC=8）では必ず指定すること**。None の場合 config の token→decimals マップで
                解決し、未知トークンは 18。
            amount_in_usd: トレード金額（USD）。portfolio_value_usd と併用必須
                （未指定時は fail-closed で拒否）。

        Returns:
            RouterV4SwapResult
        """
        guard = self._check_guards(amount_in_usd, portfolio_value_usd)
        if guard is not None:
            return guard
        effective_slippage = slippage if slippage is not None else self._DEFAULT_SLIPPAGE
        in_decimals = self._resolve_decimals(token_in, token_in_decimals)
        req = RouterV4SwapRequest(
            market_address=market_address,
            token_in=token_in,
            token_out="YT",  # noqa: S106 — トークン種別リテラル (パスワードではない)
            amount_in=amount_in,
            slippage=effective_slippage,
            receiver=receiver,
        )
        # YT は 18 桁。入力トークンのみ decimals を解決する。
        return await self._execute_swap(
            req, "swapExactTokenForYt", amount_in_decimals=in_decimals, amount_out_decimals=18
        )

    async def sell_yt(
        self,
        market_address: str,
        token_out: str,
        yt_amount_in: Decimal,
        receiver: str,
        slippage: Decimal | None = None,
        dry_run: bool = True,
        portfolio_value_usd: Decimal | None = None,
        token_out_decimals: int | None = None,
        amount_in_usd: Decimal | None = None,
    ) -> RouterV4SwapResult:
        """YT を売却する（YT → token_out swap）。

        Args:
            market_address: 対象マーケットアドレス
            token_out: 出力トークンアドレス
            yt_amount_in: 売却する YT 量（Decimal）
            receiver: 受取アドレス
            slippage: スリッページ（デフォルト 0.5% = 0.005）
            dry_run: True の場合 calldata 生成のみで tx 送信なし（デフォルト True）
            portfolio_value_usd: ポートフォリオ総額（10%上限チェック用。None でスキップ）
            token_out_decimals: 出力トークンの decimals。**非18桁トークン（USDC/USDT=6,
                WBTC=8）では必ず指定すること**。None の場合 config の token→decimals マップで
                解決し、未知トークンは 18。
            amount_in_usd: トレード金額（USD）。portfolio_value_usd と併用必須
                （未指定時は fail-closed で拒否）。

        Returns:
            RouterV4SwapResult
        """
        guard = self._check_guards(amount_in_usd, portfolio_value_usd)
        if guard is not None:
            return guard
        effective_slippage = slippage if slippage is not None else self._DEFAULT_SLIPPAGE
        out_decimals = self._resolve_decimals(token_out, token_out_decimals)
        req = RouterV4SwapRequest(
            market_address=market_address,
            token_in="YT",  # noqa: S106 — トークン種別リテラル (パスワードではない)
            token_out=token_out,
            amount_in=yt_amount_in,
            slippage=effective_slippage,
            receiver=receiver,
        )
        # YT は 18 桁。出力トークンのみ decimals を解決する。
        return await self._execute_swap(
            req, "swapExactYtForToken", amount_in_decimals=18, amount_out_decimals=out_decimals
        )

    async def buy_pt(
        self,
        market_address: str,
        token_in: str,
        amount_in: Decimal,
        receiver: str,
        slippage: Decimal | None = None,
        dry_run: bool = True,
        portfolio_value_usd: Decimal | None = None,
        token_in_decimals: int | None = None,
        amount_in_usd: Decimal | None = None,
    ) -> RouterV4SwapResult:
        """PT を購入する（token_in → PT swap）。

        Args:
            market_address: 対象マーケットアドレス
            token_in: 入力トークンアドレス
            amount_in: 入力量（Decimal）
            receiver: PT 受取アドレス
            slippage: スリッページ（デフォルト 0.5% = 0.005）
            dry_run: True の場合 calldata 生成のみで tx 送信なし（デフォルト True）
            portfolio_value_usd: ポートフォリオ総額（10%上限チェック用。None でスキップ）
            token_in_decimals: 入力トークンの decimals。**非18桁トークン（USDC/USDT=6,
                WBTC=8）では必ず指定すること**。None の場合 config の token→decimals マップで
                解決し、未知トークンは 18。
            amount_in_usd: トレード金額（USD）。portfolio_value_usd と併用必須
                （未指定時は fail-closed で拒否）。

        Returns:
            RouterV4SwapResult
        """
        guard = self._check_guards(amount_in_usd, portfolio_value_usd)
        if guard is not None:
            return guard
        effective_slippage = slippage if slippage is not None else self._DEFAULT_SLIPPAGE
        in_decimals = self._resolve_decimals(token_in, token_in_decimals)
        # Convert API は tokensOut に **PT の実アドレス**を要求する（旧 SDK のリテラル "PT" は不可）。
        # PT の decimals も config 由来（18 固定は誤り。PT-yoUSD は 6）。
        req = RouterV4SwapRequest(
            market_address=market_address,
            token_in=token_in,
            token_out=self._config.pt_token_address,
            amount_in=amount_in,
            slippage=effective_slippage,
            receiver=receiver,
        )
        return await self._execute_swap(
            req,
            "swapExactTokenForPt",
            amount_in_decimals=in_decimals,
            amount_out_decimals=self._config.pt_token_decimals,
        )

    async def sell_pt(
        self,
        market_address: str,
        token_out: str,
        pt_amount_in: Decimal,
        receiver: str,
        slippage: Decimal | None = None,
        dry_run: bool = True,
        portfolio_value_usd: Decimal | None = None,
        token_out_decimals: int | None = None,
        amount_in_usd: Decimal | None = None,
    ) -> RouterV4SwapResult:
        """PT を売却する（PT → token_out swap）。

        Args:
            market_address: 対象マーケットアドレス
            token_out: 出力トークンアドレス
            pt_amount_in: 売却する PT 量（Decimal）
            receiver: 受取アドレス
            slippage: スリッページ（デフォルト 0.5% = 0.005）
            dry_run: True の場合 calldata 生成のみで tx 送信なし（デフォルト True）
            portfolio_value_usd: ポートフォリオ総額（10%上限チェック用。None でスキップ）
            token_out_decimals: 出力トークンの decimals。**非18桁トークン（USDC/USDT=6,
                WBTC=8）では必ず指定すること**。None の場合 config の token→decimals マップで
                解決し、未知トークンは 18。
            amount_in_usd: トレード金額（USD）。portfolio_value_usd と併用必須
                （未指定時は fail-closed で拒否）。

        Returns:
            RouterV4SwapResult
        """
        guard = self._check_guards(amount_in_usd, portfolio_value_usd)
        if guard is not None:
            return guard
        effective_slippage = slippage if slippage is not None else self._DEFAULT_SLIPPAGE
        out_decimals = self._resolve_decimals(token_out, token_out_decimals)
        # tokensIn は **PT の実アドレス**（旧 SDK のリテラル "PT" は不可）。PT の decimals を
        # 18 固定にすると PT-yoUSD(6桁) で**売却数量が 10^12 倍ズレる**ため config 由来にする。
        req = RouterV4SwapRequest(
            market_address=market_address,
            token_in=self._config.pt_token_address,
            token_out=token_out,
            amount_in=pt_amount_in,
            slippage=effective_slippage,
            receiver=receiver,
        )
        return await self._execute_swap(
            req,
            "swapExactPtForToken",
            amount_in_decimals=self._config.pt_token_decimals,
            amount_out_decimals=out_decimals,
        )

    async def _execute_swap(
        self,
        req: RouterV4SwapRequest,
        sdk_endpoint: str,
        amount_in_decimals: int = 18,
        amount_out_decimals: int = 18,
    ) -> RouterV4SwapResult:
        """Convert API を呼び出して swap calldata を取得する（送信はしない）。

        外部 HTTP 失敗・Router 不一致・calldata 欠損は例外を握りつぶさず
        RouterV4SwapResult(success=False) を返す（fail-closed）。

        Args:
            req: swap リクエスト
            sdk_endpoint: 動作の識別ラベル（ログ/診断用）。Convert API は tokensIn/tokensOut から
                動作を決めるため URL には使わない（旧個別エンドポイントは廃止済み）。
            amount_in_decimals: 入力トークンの decimals（USDC=6 等の桁ズレ防止）
            amount_out_decimals: 出力トークンの decimals（amount_out 復元に使用）

        Returns:
            RouterV4SwapResult
        """
        try:
            amount_wei = self._amount_to_wei(req.amount_in, decimals=amount_in_decimals)
            # Convert API は tokensIn/tokensOut/amountsIn（複数形）。market は指定しない
            # ——対象 market は PT アドレス側で一意に決まるため。
            # slippage は小数形式で渡す（0.005 = 0.5%）。
            params: dict[str, Any] = {
                "tokensIn": req.token_in,
                "tokensOut": req.token_out,
                "amountsIn": str(amount_wei),
                "slippage": str(req.slippage),
                "receiver": req.receiver,
                "enableAggregator": self._ENABLE_AGGREGATOR,
            }

            logger.info(
                "PendleRouterV4Client._execute_swap: action=%s, market=%s, amountIn=%s",
                sdk_endpoint,
                req.market_address[:10] + "...",
                req.amount_in,
            )

            sdk_response = await self._call_sdk(params)

            # C2: calldata の宛先 (routes[0].tx.to) を Router と照合する。
            # approve の spender は照合済みの宛先で補完する（Convert API は spender を返さない）。
            router_ok, to_addr, router_err = self._verify_router(sdk_response)
            if not router_ok or not to_addr:
                logger.warning(
                    "PendleRouterV4Client._execute_swap: %s (action=%s)",
                    router_err,
                    sdk_endpoint,
                )
                return RouterV4SwapResult(success=False, error=router_err or "router mismatch")

            calldata: str = self._first_route(sdk_response).get("tx", {}).get("data", "")
            # m1: calldata 欠損/空文字は空 tx 送信の温床。success=False で拒否する。
            if not calldata:
                logger.warning(
                    "PendleRouterV4Client._execute_swap: empty calldata (action=%s)",
                    sdk_endpoint,
                )
                return RouterV4SwapResult(success=False, error="empty calldata")

            amount_out = self._extract_amount_out(
                sdk_response, req.token_out, decimals=amount_out_decimals
            )

            return RouterV4SwapResult(
                success=True,
                tx_hash=None,  # 送信は委譲 SCW 経路が二段ガードの下で行う（本クラスは calldata のみ）
                amount_out=amount_out,
                calldata=calldata,
                to=to_addr,
                approvals=self._extract_approvals(sdk_response, spender=to_addr),
            )

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "PendleRouterV4Client._execute_swap HTTP エラー: endpoint=%s, status=%d, detail=%s",
                sdk_endpoint,
                exc.response.status_code,
                exc.response.text[:200],
            )
            return RouterV4SwapResult(
                success=False,
                error=f"SDK HTTP {exc.response.status_code}: {exc.response.text[:100]}",
            )
        except Exception as exc:
            logger.warning(
                "PendleRouterV4Client._execute_swap 失敗: endpoint=%s, error=%s",
                sdk_endpoint,
                exc,
            )
            return RouterV4SwapResult(success=False, error=str(exc))

    async def build_buy_pt_swap_result(
        self,
        market_address: str,
        token_in: str,
        amount_in: Decimal,
        from_address: str,
        slippage: Decimal | None = None,
        token_in_decimals: int | None = None,
    ) -> RouterV4SwapResult:
        """[Phase D / D3] PT 購入 (swapExactTokenForPt) の **swap 結果 (approvals 付き)** を返す。

        ``build_buy_pt_tx`` は未署名 tx dict のみ返し approvals を捨てるが、SCW 委譲署名の
        batch (approve → swap) には approvals が必要なため、``RouterV4SwapResult``
        (``.to`` / ``.calldata`` / ``.approvals``) をそのまま返す。receiver/from は署名者
        (partner 本人 / SCW) に固定し PT は本人着金。``enable_onchain_write`` ガードは通さず
        (broadcast は SCW 側が行う)、SDK 呼び出し + Router 照合 + calldata 欠損の fail-closed
        は ``_execute_swap`` 内で維持する。

        Raises:
            PendleBuildTxError: from_address 空 / amount_in<=0。
        """
        if not from_address:
            raise PendleBuildTxError("from_address は必須です (署名者)")
        if amount_in <= 0:
            raise PendleBuildTxError("amount_in は正の値である必要があります")

        effective_slippage = slippage if slippage is not None else self._DEFAULT_SLIPPAGE
        in_decimals = self._resolve_decimals(token_in, token_in_decimals)
        # Convert API は tokensOut に **PT の実アドレス**を要求する（対象 market は PT で一意）。
        # 旧実装はリテラル "PT" を渡していたが、これは旧 SDK（market + tokenOut="PT"）の規約で
        # Convert API では通らない。PT の decimals も 18 固定は誤り（PT-yoUSD は 6）。
        req = RouterV4SwapRequest(
            market_address=market_address,
            token_in=token_in,
            token_out=self._config.pt_token_address,
            amount_in=amount_in,
            slippage=effective_slippage,
            receiver=from_address,  # 非カストディアル: PT は署名者本人へ着金
        )
        return await self._execute_swap(
            req,
            "swapExactTokenForPt",
            amount_in_decimals=in_decimals,
            amount_out_decimals=self._config.pt_token_decimals,
        )

    async def build_sell_pt_swap_result(
        self,
        market_address: str,
        token_out: str,
        pt_amount_in: Decimal,
        from_address: str,
        slippage: Decimal | None = None,
        token_out_decimals: int | None = None,
    ) -> RouterV4SwapResult:
        """[Phase D / D4] PT 売却/満期 redeem (swapExactPtForToken) の swap 結果を返す。

        ``build_buy_pt_swap_result`` の出口版。満期到来後は Pendle が PT→underlying を 1:1 で
        redeem する経路にルーティングする（満期前は二次市場の流動性に依存）。receiver は署名者
        本人に固定し token_out(USDC)を本人着金。approve 対象は PT トークン（SDK approvals が返す）
        で、``build_pendle_swap_calls`` が汎用に approve→swap の calls を組む。
        ``enable_onchain_write`` ガードは通さず（broadcast は SCW 側）、Router 照合・calldata 欠損
        の fail-closed は ``_execute_swap`` 内で維持する。

        Raises:
            PendleBuildTxError: from_address 空 / pt_amount_in<=0。
        """
        if not from_address:
            raise PendleBuildTxError("from_address は必須です (署名者)")
        if pt_amount_in <= 0:
            raise PendleBuildTxError("pt_amount_in は正の値である必要があります")

        effective_slippage = slippage if slippage is not None else self._DEFAULT_SLIPPAGE
        out_decimals = self._resolve_decimals(token_out, token_out_decimals)
        # tokensIn は **PT の実アドレス**（旧実装のリテラル "PT" は Convert API で通らない）。
        # PT の decimals は config 由来。ここを 18 固定にすると PT-yoUSD(6桁) で
        # **売却数量が 10^12 倍ズレる**（残高不足で失敗するか、意図しない量を売る）。
        req = RouterV4SwapRequest(
            market_address=market_address,
            token_in=self._config.pt_token_address,
            token_out=token_out,
            amount_in=pt_amount_in,
            slippage=effective_slippage,
            receiver=from_address,  # 非カストディアル: 出力トークンは署名者本人へ着金
        )
        return await self._execute_swap(
            req,
            "swapExactPtForToken",
            amount_in_decimals=self._config.pt_token_decimals,
            amount_out_decimals=out_decimals,
        )

    async def build_buy_pt_tx(
        self,
        market_address: str,
        token_in: str,
        amount_in: Decimal,
        from_address: str,
        slippage: Decimal | None = None,
        token_in_decimals: int | None = None,
    ) -> dict[str, Any]:
        """パートナー本人署名用: PT 購入 (swapExactTokenForPt) の未署名 tx を構築して返す。

        サーバー鍵で署名・broadcast しない非カストディアル経路。Hosted SDK が生成した
        calldata を未署名 tx dict にして返す。``receiver`` / ``from`` は partner 本人に固定し
        （PT は本人 wallet に着金）、SDK calldata の ``tx.to`` / approvals.spender が Router
        であることを ``_execute_swap`` 内で照合する。

        ``enable_onchain_write`` ガード（``buy_pt`` 経由の ``_check_guards``）は **サーバー
        broadcast** を二段ガードするためのもの。本メソッドはサーバー broadcast を行わず
        partner が Privy で送信するため、当該ガードは適用しない（Router 照合・calldata
        欠損チェックは維持する fail-closed）。

        Args:
            market_address: 対象 Pendle マーケットアドレス。
            token_in: 支払いに使う入力トークンアドレス（partner が保有・approve 済み前提）。
            amount_in: 入力量（Decimal）。
            from_address: 署名者（partner 本人）= PT 受取アドレス。
            slippage: スリッページ（デフォルト 0.5% = 0.005）。
            token_in_decimals: 入力トークンの decimals（USDC=6 等の桁ズレ防止）。

        Returns:
            {"to", "data", "from", "chainId", "value"} 形式の未署名 tx dict（value="0x0"）。

        Raises:
            PendleBuildTxError: calldata 取得失敗 / Router 不一致 / 引数不正。
        """
        # swap 結果 (approvals 付き) を取得し、未署名 tx dict に整形する。前提チェック
        # (from_address 空 / amount_in<=0) と enable_onchain_write 非適用は共通実装に集約。
        result = await self.build_buy_pt_swap_result(
            market_address=market_address,
            token_in=token_in,
            amount_in=amount_in,
            from_address=from_address,
            slippage=slippage,
            token_in_decimals=token_in_decimals,
        )
        if not result.success or not result.calldata or not result.to:
            raise PendleBuildTxError(result.error or "未署名 tx の calldata 取得に失敗しました")
        return {
            "to": result.to,
            "data": result.calldata,
            "from": from_address,
            "chainId": self._chain_id,
            "value": "0x0",  # ERC20 入力のため native value なし
        }

    async def add_liquidity(
        self,
        market_address: str,
        token_in: str,
        amount_in: Decimal,
        receiver: str,
        slippage: Decimal | None = None,
        dry_run: bool = True,
        portfolio_value_usd: Decimal | None = None,
        token_in_decimals: int | None = None,
        amount_in_usd: Decimal | None = None,
    ) -> RouterV4AddLiquidityResult:
        """マーケットに流動性を追加する（token_in → LP）。

        Args:
            market_address: 対象マーケットアドレス
            token_in: 入力トークンアドレス
            amount_in: 入力量（Decimal）
            receiver: LP 受取アドレス
            slippage: スリッページ（デフォルト 0.5% = 0.005）
            dry_run: True の場合 calldata 生成のみで tx 送信なし（デフォルト True）
            portfolio_value_usd: ポートフォリオ総額（10%上限チェック用。None でスキップ）
            token_in_decimals: 入力トークンの decimals。**非18桁トークン（USDC/USDT=6,
                WBTC=8）では必ず指定すること**。None の場合 config の token→decimals マップで
                解決し、未知トークンは 18。
            amount_in_usd: トレード金額（USD）。portfolio_value_usd と併用必須
                （未指定時は fail-closed で拒否）。

        Returns:
            RouterV4AddLiquidityResult
        """
        guard_liq = self._check_guards_liq(amount_in_usd, portfolio_value_usd)
        if guard_liq is not None:
            return guard_liq

        effective_slippage = slippage if slippage is not None else self._DEFAULT_SLIPPAGE
        in_decimals = self._resolve_decimals(token_in, token_in_decimals)
        req = RouterV4AddLiquidityRequest(
            market_address=market_address,
            token_in=token_in,
            amount_in=amount_in,
            slippage=effective_slippage,
            receiver=receiver,
        )

        try:
            amount_wei = self._amount_to_wei(req.amount_in, decimals=in_decimals)
            # Convert API は tokensOut に market(LP) アドレスを渡すと action="add-liquidity" になる
            # （swap と同一エンドポイント。実 API で確認済み 2026-07-17）。
            params: dict[str, Any] = {
                "tokensIn": req.token_in,
                "tokensOut": req.market_address,
                "amountsIn": str(amount_wei),
                "slippage": str(req.slippage),
                "receiver": req.receiver,
                "enableAggregator": self._ENABLE_AGGREGATOR,
            }

            logger.info(
                "PendleRouterV4Client.add_liquidity: market=%s, tokenIn=%s, amountIn=%s",
                req.market_address[:10] + "...",
                req.token_in[:10] + "..." if len(req.token_in) > 10 else req.token_in,
                req.amount_in,
            )

            sdk_response = await self._call_sdk(params)

            # C2: routes[0].tx.to を Router と照合する（spender は照合済み宛先で補完）。
            router_ok, to_addr, router_err = self._verify_router(sdk_response)
            if not router_ok or not to_addr:
                logger.warning("PendleRouterV4Client.add_liquidity: %s", router_err)
                return RouterV4AddLiquidityResult(
                    success=False, error=router_err or "router mismatch"
                )

            calldata = self._first_route(sdk_response).get("tx", {}).get("data", "")
            # m1: calldata 欠損/空文字は拒否（空 tx 送信の温床）。
            if not calldata:
                logger.warning("PendleRouterV4Client.add_liquidity: empty calldata")
                return RouterV4AddLiquidityResult(success=False, error="empty calldata")

            # LP トークンは 18 桁。outputs の token は market(LP) アドレス。
            lp_amount = self._extract_amount_out(sdk_response, req.market_address, decimals=18)

            return RouterV4AddLiquidityResult(
                success=True,
                tx_hash=None,  # 送信は行わない（calldata 取得のみ）
                lp_amount=lp_amount,
                calldata=calldata,
                to=to_addr,
                approvals=self._extract_approvals(sdk_response, spender=to_addr),
            )

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "PendleRouterV4Client.add_liquidity HTTP エラー: status=%d, detail=%s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return RouterV4AddLiquidityResult(
                success=False,
                error=f"SDK HTTP {exc.response.status_code}: {exc.response.text[:100]}",
            )
        except Exception as exc:
            logger.warning("PendleRouterV4Client.add_liquidity 失敗: error=%s", exc)
            return RouterV4AddLiquidityResult(success=False, error=str(exc))


def get_pendle_router_v4_client(config: PendleConfig) -> PendleRouterV4Client:
    """設定から PendleRouterV4Client を生成して返す。

    service 層から到達可能な単一エントリポイント。
    automation には配線しない。main.py 変更禁止のため router.py で使用する。
    """
    return PendleRouterV4Client(config)


def get_pendle_client(config: PendleConfig) -> AbstractPendleClient:
    """設定に基づいて適切な PendleClient を返す。"""
    import os  # noqa: PLC0415

    app_env = os.getenv("APP_ENV", "development")
    if app_env == "production" and config.sandbox:
        logger.error("DummyClient is forbidden in %s environment", app_env)
        raise RuntimeError(f"DummyClient cannot be used in {app_env} environment")
    if config.sandbox:
        logger.warning("Using DummyClient — not for production")
        return DummyPendleClient(config)
    logger.info("Using PendleWebClient (Pendle REST API)")
    return PendleWebClient(config)
