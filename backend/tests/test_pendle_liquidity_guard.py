# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_pendle_liquidity_guard.py
"""[Phase D / D5] 流動性ガード (_pendle_liquidity_blocked)。

1 投入がプール流動性(tvl_usd)の数% + 絶対上限を超えないことを検査し、tvl 未知(API失敗/0)は
fail-closed で block することを検証する。
"""

import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-pendle-liq")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.protocols.pendle.client as pendle_client_mod  # noqa: E402
from app.proposals.router import _pendle_liquidity_blocked  # noqa: E402
from app.protocols.pendle.config import (  # noqa: E402
    PENDLE_MAX_TRADE_USD_HARD_MAX,
    PendleConfig,
)

_MARKET = "0x1111111111111111111111111111111111111111"
_PT = "0x2222222222222222222222222222222222222222"
_OTHER_PT = "0x3333333333333333333333333333333333333333"
_PT_DECIMALS = 6  # PT-yoUSD 相当（PT は 18 桁とは限らない）


def _config(**overrides: object) -> PendleConfig:
    kwargs: dict = {
        "market_address": _MARKET,
        "pt_token_address": _PT,
        "pt_token_decimals": _PT_DECIMALS,
        "max_pool_liquidity_pct": Decimal("0.05"),
        "max_trade_usd_cap": Decimal("5000"),
    }
    kwargs.update(overrides)
    return PendleConfig(**kwargs)


def _patch_market(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tvl: object,
    raises: bool = False,
    pt_address: object = _PT,
    pt_decimals: object = _PT_DECIMALS,
    days_to_maturity: int = 68,  # PT-yoUSD-24SEP2026 相当（min 7 を満たす）
) -> None:
    class _Client:
        async def get_market_info(self, market_address: str) -> object:
            if raises:
                raise RuntimeError("pendle API down")
            return SimpleNamespace(
                tvl_usd=tvl,
                pt_address=pt_address,
                pt_decimals=pt_decimals,
                days_to_maturity=days_to_maturity,
            )

    monkeypatch.setattr(pendle_client_mod, "get_pendle_client", lambda cfg: _Client())


def test_pass_when_within_pool_and_abs_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """tvl 十分・amount ≤ 5% かつ ≤ 絶対上限 → None(通過)。"""
    _patch_market(monkeypatch, tvl=Decimal("114000"))
    assert _pendle_liquidity_blocked(_config(), Decimal("1000")) is None


def test_block_when_exceeds_pool_pct(monkeypatch: pytest.MonkeyPatch) -> None:
    """amount > tvl×5%(=5700) → block。"""
    _patch_market(monkeypatch, tvl=Decimal("114000"))
    reason = _pendle_liquidity_blocked(_config(), Decimal("6000"))
    assert reason is not None and "プール流動性上限" in reason


def test_block_when_exceeds_abs_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """pool% は満たすが絶対上限 5000 を超える → block。"""
    _patch_market(monkeypatch, tvl=Decimal("1000000"))  # 5% = 50000 で余裕
    reason = _pendle_liquidity_blocked(_config(), Decimal("6000"))
    assert reason is not None and "絶対上限" in reason


def test_block_when_tvl_zero_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """tvl=0(API失敗の fail-open 値) → fail-closed で block。"""
    _patch_market(monkeypatch, tvl=Decimal("0"))
    reason = _pendle_liquidity_blocked(_config(), Decimal("1"))
    assert reason is not None and "fail-closed" in reason


def test_block_when_market_info_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_market_info 例外 → fail-closed で block(壊さない保証ができない)。"""
    _patch_market(monkeypatch, tvl=Decimal("0"), raises=True)
    reason = _pendle_liquidity_blocked(_config(), Decimal("1000"))
    assert reason is not None and "fail-closed" in reason


# ---------------------------------------------------------------------------
# [安全レビュー H2/M2] market と PT の対応検証
#
# PENDLE_MARKET_ADDRESS(本ガードが流動性を見る対象) と PENDLE_PT_TOKEN_ADDRESS(実際に買う対象
# = Convert API の tokensOut) は独立した env で、swap 呼び出しに market は送られない。両者が
# 別 market を指すと「ガードは別プールの流動性を承認する」状態になり、ガードが PASS と報告
# しながら実際は薄いプールへ過大投入し得る。運用者の注意力を安全装置にしない。
# ---------------------------------------------------------------------------


def test_block_when_market_pt_mismatches_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """market が扱う PT と PENDLE_PT_TOKEN_ADDRESS が不一致 → fail-closed。

    満期ロールで PT だけ更新し market を更新し忘れた場合を想定。旧実装では「$114k プールの
    5%」を承認しつつ、実際は別プールへ投入していた。
    """
    _patch_market(monkeypatch, tvl=Decimal("114000"), pt_address=_OTHER_PT)
    reason = _pendle_liquidity_blocked(_config(), Decimal("100"))
    assert reason is not None and "不一致" in reason


def test_block_when_market_pt_unresolvable(monkeypatch: pytest.MonkeyPatch) -> None:
    """market の PT アドレスが取れない → 対応を検証できないので fail-closed。"""
    _patch_market(monkeypatch, tvl=Decimal("114000"), pt_address=None)
    reason = _pendle_liquidity_blocked(_config(), Decimal("100"))
    assert reason is not None and "PT アドレスを解決できない" in reason


def test_pt_address_comparison_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """checksum 表記の違いだけでは block しないこと（誤検知で運用を止めない）。"""
    _patch_market(monkeypatch, tvl=Decimal("114000"), pt_address=_PT.upper())
    assert _pendle_liquidity_blocked(_config(), Decimal("100")) is None


def test_block_when_pt_decimals_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """実 PT decimals と設定が不一致 → fail-closed（silent under-sell 防止）。

    decimals が実際より低いと SELL_PT は dust だけ売って **成功扱いで記録される**
    （$10k 売却のつもりが実質ゼロ）。高すぎる側は revert するが、低い側は黙って通るため
    ここで止める。
    """
    _patch_market(monkeypatch, tvl=Decimal("114000"), pt_decimals=18)
    reason = _pendle_liquidity_blocked(_config(), Decimal("100"))
    assert reason is not None and "decimals" in reason


def test_default_abs_cap_is_small(monkeypatch: pytest.MonkeyPatch) -> None:
    """[安全レビュー H3] env 未設定時の絶対上限が小さいこと。

    Pendle 経路では単一10%/日次30%(CLAUDE.md Rule 3/4)が実際には効いていないため、絶対上限が
    唯一の金額ガードになる。既定 5000 だと env 設定を忘れた運用者に $5,000 の枠が黙って開く。
    """
    monkeypatch.delenv("PENDLE_MAX_TRADE_USD_CAP", raising=False)
    assert PendleConfig().max_trade_usd_cap == Decimal("20")

    _patch_market(monkeypatch, tvl=Decimal("1000000"))  # pool 5% = 50000 で余裕
    cfg = _config(max_trade_usd_cap=PendleConfig().max_trade_usd_cap)
    reason = _pendle_liquidity_blocked(cfg, Decimal("100"))
    assert reason is not None and "絶対上限" in reason


# ---------------------------------------------------------------------------
# [安全レビュー N1/N2/P1] 満期ガード / decimals 不明 / hard clamp
# ---------------------------------------------------------------------------


def test_block_when_past_or_near_maturity(monkeypatch: pytest.MonkeyPatch) -> None:
    """満期が近い/過ぎた market は fail-closed（N1）。

    `min_days_to_maturity` は service.py / cache.py にしか無く、broadcast 経路は
    config.market_address を直参照するため通らなかった。本 PR で経路が live になった結果
    素通りするようになったため、ガードに追加した。満期後 BUY_PT は revert(gas 損)、
    満期直前は利回りほぼゼロで資金をロックして「成功」記録だけ残る。
    """
    _patch_market(monkeypatch, tvl=Decimal("114000"), days_to_maturity=3)
    reason = _pendle_liquidity_blocked(_config(), Decimal("10"))
    assert reason is not None and "満期" in reason


def test_pass_when_maturity_far_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    """min_days_to_maturity(既定7) を満たせば通過。"""
    _patch_market(monkeypatch, tvl=Decimal("114000"), days_to_maturity=68)
    assert _pendle_liquidity_blocked(_config(), Decimal("10")) is None


def test_block_when_pt_decimals_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """decimals が取れない場合も fail-closed（N2）。

    「verify すると書いた項目が API 次第で無言スキップされる」構造は H2 を生んだ原因と同型。
    """
    _patch_market(monkeypatch, tvl=Decimal("114000"), pt_decimals=None)
    reason = _pendle_liquidity_blocked(_config(), Decimal("10"))
    assert reason is not None and "decimals を解決できない" in reason


class TestMaxTradeUsdCapHardClamp:
    """[P1] env で越えられない絶対上限。cap は唯一の金額ガードなので第二層が要る。"""

    def test_env_cannot_exceed_hard_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env のタイポ (20 → 200000) が hard clamp で頭打ちになること。"""
        monkeypatch.setenv("PENDLE_MAX_TRADE_USD_CAP", "200000")
        assert PendleConfig().max_trade_usd_cap == PENDLE_MAX_TRADE_USD_HARD_MAX

    def test_env_below_hard_max_is_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PENDLE_MAX_TRADE_USD_CAP", "50")
        assert PendleConfig().max_trade_usd_cap == Decimal("50")

    def test_infinity_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`Decimal("inf")` はパース成功し `amount > inf` が常に False = ガード無効化。

        有限値でなければ default に倒す。
        """
        monkeypatch.setenv("PENDLE_MAX_TRADE_USD_CAP", "inf")
        assert PendleConfig().max_trade_usd_cap == Decimal("20")

    def test_nan_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NaN も比較が常に False になるため default に倒す。"""
        monkeypatch.setenv("PENDLE_MAX_TRADE_USD_CAP", "NaN")
        assert PendleConfig().max_trade_usd_cap == Decimal("20")

    def test_garbage_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PENDLE_MAX_TRADE_USD_CAP", "not-a-number")
        assert PendleConfig().max_trade_usd_cap == Decimal("20")
