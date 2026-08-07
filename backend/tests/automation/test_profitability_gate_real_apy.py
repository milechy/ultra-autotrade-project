# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_profitability_gate_real_apy.py
"""採算ゲートが実APYを使うことの単体テスト (2026-08-08 Asana 1217292671266767)。

以前は `_default_apy = Decimal("4")` を常に使い、同じスコープで取得済みの実APY
(`aave_data["supply_apy"]`) を無視していた。実測 APY 3.2648%（2026-08-08 Base mainnet）
では $100 の提案は赤字（30日利益$0.2683 - ガス代$0.27 = -$0.0017）だが、固定4%では
「利益+$0.05」と誤判定され本番で実際に作成された
(user 19, `[funding_funnel] user_id=19 balance=$0 < min $1000 — $100.00 の提案を作成`)。

本テストは `calculate_fee_by_market` を**モックしない**（test_safe_yield_on_hold.py 等の
既存テストとの違い）。ここで検証したいのは「実APYが正しく渡り、実際の採算計算に
反映されるか」そのものなので、fee 計算自体をモックすると意味が消える。
"""

import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-profitability-gate")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.automation.ai_judgment_scheduler as sched  # noqa: E402
from app.automation.ai_judgment_scheduler import (  # noqa: E402
    _create_safe_yield_proposals_for_users,
    _resolve_effective_supply_apy,
)
from app.proposals.models import Proposal  # noqa: E402

# 2026-08-08 実測値 (Base mainnet, Aave V3 Pool.getReserveData(USDC).currentLiquidityRate)。
_REAL_MEASURED_APY = Decimal("3.2648")


def _mk_user(uid: int = 21) -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.tier = "LOWER"
    u.risk_mode = "conservative"
    return u


def _mk_db(users: list, pending: int = 0) -> MagicMock:
    db = MagicMock()
    active_res = MagicMock()
    active_res.all.return_value = users
    stale_res = MagicMock()
    stale_res.all.return_value = []
    db.scalars.side_effect = [active_res] + [stale_res for _ in range(len(users) * 2)]
    db.scalar.return_value = pending
    return db


def _added_proposals(db: MagicMock) -> list:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Proposal)]


def _patch_non_gate_deps(monkeypatch: pytest.MonkeyPatch, *, amount: Decimal) -> None:
    """採算ゲート以外の依存だけをモックする (fee計算は実物を使う)。"""
    monkeypatch.setattr(sched, "_is_user_due_for_judgment", lambda u, now: True)
    monkeypatch.setattr(
        sched, "_resolve_proposal_amount", lambda db, uid, supply_apy_pct=None: amount
    )
    monkeypatch.setattr(
        sched, "normalize_tier", lambda tier, user_id=None: MagicMock(value="LOWER")
    )
    monkeypatch.setattr(sched, "estimate_static_gas_cost_usd", lambda op: Decimal("2"))
    monkeypatch.setattr("app.notifications.factory.get_notification_service", lambda: MagicMock())


def _decision() -> MagicMock:
    d = MagicMock()
    d.id = 1
    return d


def _result() -> MagicMock:
    r = MagicMock()
    r.final_confidence = 50
    return r


class TestResolveEffectiveSupplyApy:
    """_resolve_effective_supply_apy (両関数が共有する解決ロジック) の単体テスト。"""

    def test_正の実APYはそのまま使う(self) -> None:
        assert _resolve_effective_supply_apy(_REAL_MEASURED_APY) == _REAL_MEASURED_APY

    def test_Noneはフォールバック値になる(self) -> None:
        assert _resolve_effective_supply_apy(None) == sched._FALLBACK_SUPPLY_APY_PCT

    def test_0はフォールバック値になる(self) -> None:
        assert _resolve_effective_supply_apy(Decimal("0")) == sched._FALLBACK_SUPPLY_APY_PCT

    def test_負値はフォールバック値になる(self) -> None:
        assert _resolve_effective_supply_apy(Decimal("-1.5")) == sched._FALLBACK_SUPPLY_APY_PCT

    def test_フォールバック使用時にwarningログが出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING"):
            _resolve_effective_supply_apy(None)
        assert any("フォールバック" in r.message for r in caplog.records)

    def test_正常値ではwarningログが出ない(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING"):
            _resolve_effective_supply_apy(_REAL_MEASURED_APY)
        assert not any("フォールバック" in r.message for r in caplog.records)


class TestProfitabilityGateUsesRealApy:
    """★中核: 採算ゲートの実際の判定に実APYが反映されること (end-to-end, fee計算は実物)。"""

    def test_実測APY3_2648パーセントでは100ドル提案がブロックされる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """本番で実際に起きた事故の再現: 固定4%なら通るが実APYでは赤字。"""
        _patch_non_gate_deps(monkeypatch, amount=Decimal("100"))
        db = _mk_db([_mk_user()], pending=0)
        n = _create_safe_yield_proposals_for_users(
            db, _decision(), _result(), supply_apy_pct=_REAL_MEASURED_APY
        )
        assert n == 0
        assert _added_proposals(db) == []

    def test_APY4_5パーセントなら100ドル提案は通る(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ゲートを閉じすぎていないことの回帰確認 (実APYが十分高ければ通る)。"""
        _patch_non_gate_deps(monkeypatch, amount=Decimal("100"))
        db = _mk_db([_mk_user()], pending=0)
        n = _create_safe_yield_proposals_for_users(
            db, _decision(), _result(), supply_apy_pct=Decimal("4.5")
        )
        assert n == 1
        assert len(_added_proposals(db)) == 1

    def test_supply_apy_pctがNoneならフォールバック3パーセントで判定される(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RPC失敗等で実APYが取れない場合、フォールバック(3.0%)でも$100は赤字なのでブロック。

        フォールバック値自体が保守的 (実勢を上回らない) であることの確認でもある。
        """
        _patch_non_gate_deps(monkeypatch, amount=Decimal("100"))
        db = _mk_db([_mk_user()], pending=0)
        n = _create_safe_yield_proposals_for_users(db, _decision(), _result(), supply_apy_pct=None)
        assert n == 0
        assert _added_proposals(db) == []

    def test_supply_apy_pctが0でも例外を投げずフォールバックへ倒れる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_non_gate_deps(monkeypatch, amount=Decimal("100"))
        db = _mk_db([_mk_user()], pending=0)
        # 例外が伝播しないことそのものが検証対象。
        n = _create_safe_yield_proposals_for_users(
            db, _decision(), _result(), supply_apy_pct=Decimal("0")
        )
        assert n == 0

    def test_supply_apy_pctが負値でも例外を投げずフォールバックへ倒れる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_non_gate_deps(monkeypatch, amount=Decimal("100"))
        db = _mk_db([_mk_user()], pending=0)
        n = _create_safe_yield_proposals_for_users(
            db, _decision(), _result(), supply_apy_pct=Decimal("-2")
        )
        assert n == 0

    def test_高いAPYでは少額でも通る(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """極端値でも破綻しないこと。APYが十分高ければ$50でも黒字になり得る。"""
        _patch_non_gate_deps(monkeypatch, amount=Decimal("50"))
        db = _mk_db([_mk_user()], pending=0)
        n = _create_safe_yield_proposals_for_users(
            db, _decision(), _result(), supply_apy_pct=Decimal("20")
        )
        assert n == 1


class TestBothProposalPathsShareTheSameApyResolution:
    """BUY/SELL経路 (_create_proposals_for_users) も同じ実APYを使うことのパリティ確認。

    2つの関数は _resolve_effective_supply_apy を共有しているが、片方だけ配線を
    誤って忘れる (コピペミス) 事故を防ぐため、もう一方の経路でも同一挙動を確認する。
    """

    def test_BUY_SELL経路でも実測APYで100ドル提案がブロックされる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.ai.schemas import TradeAction
        from app.automation.ai_judgment_scheduler import _create_proposals_for_users

        _patch_non_gate_deps(monkeypatch, amount=Decimal("100"))
        monkeypatch.setattr(sched, "_should_skip_unreachable_approval_user", lambda db, u: False)
        db = _mk_db([_mk_user()], pending=0)
        result = _result()
        result.final_action = TradeAction.BUY
        result.final_reason = "test"
        n = _create_proposals_for_users(db, _decision(), result, supply_apy_pct=_REAL_MEASURED_APY)
        assert n == 0
        assert _added_proposals(db) == []
