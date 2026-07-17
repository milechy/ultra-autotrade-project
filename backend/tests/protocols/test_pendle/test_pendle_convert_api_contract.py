# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Pendle Convert API の **契約テスト（実 API 疎通）**。

## なぜ必要か

2026-07-17 まで、Pendle の calldata クライアントは **実在しない API** に対して書かれていた
（`/sdk/api/v1/{chain}/swapExactTokenForPt` → 全チェーンで 404）。URL・パラメータ名・応答形の
すべてが実物と食い違っていたが、以下の理由で誰も検出できなかった:

  1. 全経路が dormant（本番で一度も呼ばれない）
  2. ユニットテストが `_call_sdk` をモックしており、**架空の応答形を自分で固定していた**

つまり「テストは通るが実 API では必ず 404」という状態だった。本ファイルは実 API を叩いて
**モックが実物とズレたら落ちる**ようにするための契約テスト。ユニットテストの mock 形は
`convert_api_fixtures.convert_response()` に集約してあり、本テストがその形の正しさを担保する。

## 実行方法

外部ネットワークに依存するため既定では skip する（CI/オフラインで落とさない）::

    PENDLE_LIVE_API_TEST=1 pytest tests/protocols/test_pendle/test_pendle_convert_api_contract.py -v

**読み取り専用・無料・鍵不要・broadcast なし**（GET で calldata を組み立てるだけ）。
実資金は 1 wei も動かない。

## 既知の制約（実 API で確認済み 2026-07-17）

- **Pendle は mainnet のみ対応**。testnet（Base Sepolia 84532 / Arbitrum Sepolia 421614）は
  400 "Unsupported chain id" で拒否される ＝ **testnet 上での検証経路は存在しない**。
- SELL_PT(PT→USDC) は `enableAggregator=true` が必須（false だと
  "tokenOut must be in the SY token out list" で 400）。ただし aggregator 有効でも
  `tx.to` は RouterV4 のままで、宛先 allowlist の fail-closed 性は保たれる。
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.protocols.pendle.client import PendleRouterV4Client
from app.protocols.pendle.config import PendleConfig

pytestmark = pytest.mark.skipif(
    os.getenv("PENDLE_LIVE_API_TEST") != "1",
    reason="実 API 疎通テスト。PENDLE_LIVE_API_TEST=1 で有効化する",
)

# Base Mainnet / PT-yoUSD-24SEP2026（Phase-D D1 で採用した初期ターゲット）
_CHAIN = "base"
_MARKET = "0x250c15e59a7572195e248f668636723cca20a2b8"
_PT = "0x1fec97ca2817da87f266fd1741bba61caf7cde29"
_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"
# 実在するが残高不要の受取先（calldata 生成は残高を見ない）。
_RECEIVER = "0x7f93f4Ba0eDf3b0D18a3fF4c9Ba1D5C5CBD8a0Ff"


def _client() -> PendleRouterV4Client:
    config = PendleConfig(sandbox=False)
    config.chain = _CHAIN
    config.router_address = _ROUTER
    config.underlying_token_address = _USDC
    config.pt_token_address = _PT
    config.pt_token_decimals = 6  # PT-yoUSD-24SEP2026 は 6 桁（18 ではない）
    config.underlying_token_decimals = 6  # USDC
    config.market_address = _MARKET
    config.stable_underlying = True
    # calldata 取得のみ（broadcast はしない）。Q1 ガードを通すため True。
    config.enable_onchain_write = True
    return PendleRouterV4Client(config)


@pytest.mark.asyncio
async def test_buy_pt_live_calldata_targets_router() -> None:
    """USDC → PT-yoUSD の calldata が実 API から取得でき、宛先が RouterV4 であること。"""
    client = _client()
    result = await client.build_buy_pt_swap_result(
        market_address=_MARKET,
        token_in=_USDC,
        amount_in=Decimal("1"),  # 1 USDC
        from_address=_RECEIVER,
        token_in_decimals=6,
    )
    assert result.success is True, f"live SDK 失敗: {result.error}"
    assert result.to is not None and result.to.lower() == _ROUTER.lower()
    assert result.calldata and result.calldata.startswith("0x")
    # 1 USDC で 1 PT 前後（PT は満期前ディスカウントで $1 未満 → 1 USDC で 1 超の PT）
    assert result.amount_out is not None and result.amount_out > Decimal("0")


@pytest.mark.asyncio
async def test_buy_pt_live_approval_spender_is_verified_router() -> None:
    """approve は「照合済み Router 宛」に限られること。

    Convert API は spender を返さないため、client が tx.to（Router 照合済み）で補完する。
    ここが崩れると任意コントラクトへ approve する余地が生まれる。
    """
    client = _client()
    result = await client.build_buy_pt_swap_result(
        market_address=_MARKET,
        token_in=_USDC,
        amount_in=Decimal("1"),
        from_address=_RECEIVER,
        token_in_decimals=6,
    )
    assert result.success is True, f"live SDK 失敗: {result.error}"
    assert result.approvals, "USDC の approve が要求されるはず"
    for approval in result.approvals:
        assert approval.token is not None
        assert approval.token.lower() == _USDC.lower()
        assert approval.spender is not None
        assert approval.spender.lower() == _ROUTER.lower()


@pytest.mark.asyncio
async def test_sell_pt_live_calldata_targets_router() -> None:
    """PT-yoUSD → USDC（満期出口）の calldata も実 API から取得できること。

    SELL_PT は aggregator が必須（yoUSD→USDC 変換）。それでも tx.to は Router のまま。
    """
    client = _client()
    result = await client.build_sell_pt_swap_result(
        market_address=_MARKET,
        token_out=_USDC,
        pt_amount_in=Decimal("1"),
        from_address=_RECEIVER,
        token_out_decimals=6,
    )
    assert result.success is True, f"live SDK 失敗: {result.error}"
    assert result.to is not None and result.to.lower() == _ROUTER.lower()
    assert result.calldata and result.calldata.startswith("0x")
    assert result.amount_out is not None and result.amount_out > Decimal("0")


@pytest.mark.asyncio
async def test_market_info_live_returns_real_liquidity() -> None:
    """流動性ガードの基準（tvl_usd）が実データで取れること。

    `PendleWebClient` の chain map に "base" が無かった頃は 42161(Arbitrum) を叩いて 404 →
    except 節のフォールバック（**stETH / tvl=0 / APY 5.2% の架空値**）が返っていた。
    tvl=0 は流動性ガードが全 block する値なので、Pendle は「静かに常時 block」だった。
    加えて expiry は ISO8601 文字列なのに int() でパースしており、これ単体でも必ず
    フォールバックに落ちていた。両方直った状態を実データで固定する。
    """
    from app.protocols.pendle.client import PendleWebClient

    config = PendleConfig(sandbox=False)
    config.chain = _CHAIN
    info = await PendleWebClient(config).get_market_info(_MARKET)

    assert info.underlying_asset == "yoUSD", "フォールバック(stETH)が返っている"
    assert info.tvl_usd > Decimal("0"), "tvl=0 では流動性ガードが全 block する"
    assert info.implied_apy > Decimal("0")
    # PT-yoUSD-24SEP2026
    assert info.maturity.year == 2026 and info.maturity.month == 9
    assert info.days_to_maturity > 0


@pytest.mark.asyncio
async def test_testnet_is_not_supported_by_pendle() -> None:
    """**Pendle に testnet は無い**ことを実 API で固定する。

    「Sepolia で安全に実証してから本番」という運用計画が立てられないことの根拠。
    将来 Pendle が testnet を提供したら本テストが落ちるので、その時に運用計画を見直す。
    """
    client = _client()
    client._chain_id = 84532  # Base Sepolia
    result = await client.build_buy_pt_swap_result(
        market_address=_MARKET,
        token_in=_USDC,
        amount_in=Decimal("1"),
        from_address=_RECEIVER,
        token_in_decimals=6,
    )
    assert result.success is False
    assert result.error is not None
    # 400 "Unsupported chain id ..." が返る（fail-closed で success=False）
    assert "400" in result.error or "chain" in result.error.lower()
