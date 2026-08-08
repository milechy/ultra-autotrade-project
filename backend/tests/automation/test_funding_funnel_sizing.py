# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_funding_funnel_sizing.py
"""入金前ユーザーへの推奨運用額ベース提案（docs/62 承認→入金→署名ファネル）のテスト。

## なぜこの経路が必要か

提案額は従来 **現残高 × 10%** で決めていた。しかしそれでは入金前・少額のユーザーに
意味のある提案を出せない:

    残高 $200 → 提案 $20（下限 $50 に切上）→ 30日利益 $0.16 < ガス代 $0.27 → 採算ゲートで却下

「$852 の実効下限」の正体は **10%ルール × ガス代**であって、モード（おまかせ/承認）とは
無関係だった。そのため入金ゲートを下げるだけでは何も解決しない。

そこで入金前は分母を「現残高」ではなく「推奨運用額（MIN_DEPOSIT_USD）」に置き換える。

## 安全性の要（このファイルの主目的）

推奨運用額ベースで提案を作ると、**提案額が現残高を上回る**状態が正常系として発生する。
着金検知が `balance >= amount_usd` だけを見ていると、残高 $150 のユーザーの $100 提案が
承認され **総資産の 67% を 1 取引で supply** してしまう
（CLAUDE.md [CRITICAL] 3「Max single trade: 10% of total assets」違反）。

最低入金額の再検証が入っていることを固定するのが本テストの中心。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-funding-funnel")

from app.auth.models import User  # noqa: E402
from app.automation import ai_judgment_scheduler as sched  # noqa: E402
from app.automation.ai_judgment_scheduler import (  # noqa: E402
    _PROPOSAL_RATIO,
    _notify_deposit_gap_if_needed,
    _resolve_proposal_amount,
)
from app.automation.scheduled_tasks import run_funding_detection_once  # noqa: E402
from app.database import Base  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402
from app.users.deposit_policy import MIN_DEPOSIT_USD  # noqa: E402

# get_notification_service は関数内 import のため import 元を差し替える
# (tests/automation/test_unreachable_approval_user_gate.py と同じ理由・同じパターン)。
_FACTORY = "app.notifications.factory.get_notification_service"

_SCHED = "app.automation.ai_judgment_scheduler"
_TASKS = "app.automation.scheduled_tasks"


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        os.unlink(path)


def _make_user(db: Session, uid: int) -> User:
    """非カストディアル消費者（allocation 不在 / wallet あり / SCW なし）。"""
    user = User(
        id=uid,
        email=f"funnel{uid}@test.com",
        username=f"funnel{uid}",
        hashed_password="x",
        role="viewer",
        is_active=True,
        wallet_address="0x" + f"{uid:040x}",
        execution_policy="require_approval",
    )
    db.add(user)
    db.flush()
    return user


class _NoCloseSession:
    """テスト用セッションを本番コードの `db.close()` で閉じさせないためのラッパ。

    閉じられるとテスト側の `refresh()` で状態を検証できなくなる。close 以外は委譲する。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def close(self) -> None:  # 本番コードの finally: db.close() を無効化
        pass

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)


def _make_awaiting_proposal(db: Session, uid: int, amount: Decimal) -> Proposal:
    now = datetime.now(timezone.utc)
    p = Proposal(
        user_id=uid,
        operation="SUPPLY",
        asset="USDC",
        amount=amount,  # USDC は 1:1 なので amount_usd と同値で足りる
        amount_usd=amount,
        status="awaiting_funds",
        reason="test",
        expires_at=now + timedelta(days=7),
    )
    db.add(p)
    db.flush()
    return p


class TestFunnelSizing:
    def test_入金前ユーザーには推奨運用額ベースの提案額が返る(self, db_session: Session) -> None:
        """従来は Decimal(0)（提案なし）だった。ファネルが成立しない原因だった箇所。

        2026-08-08 (Asana 1217292389876406): ファネル額は実APY連動になった。
        APY=4% (固定4%前提だった旧仕様と同値) では必要額 ($89.42) が
        $1,000×10%=$100 の基準額を下回るため、基準額 $100 のまま変わらないことを確認する。
        """
        _make_user(db_session, 601)
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=Decimal("200")):
            amount = _resolve_proposal_amount(db_session, 601, supply_apy_pct=Decimal("4"))
        assert amount == (MIN_DEPOSIT_USD * _PROPOSAL_RATIO).quantize(Decimal("0.01"))

    def test_ファネル提案額は採算ゲートを通過できる(self, db_session: Session) -> None:
        """通らない額を提案しても意味がない（$50 だと利益 $0.16 < ガス代 $0.27 で必ず却下）。"""
        from app.fees.trade_gate import calculate_fee_by_market

        _make_user(db_session, 602)
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=Decimal("0")):
            amount = _resolve_proposal_amount(db_session, 602)
        expected_profit = amount * Decimal("4") / Decimal("100") * Decimal("30") / Decimal("365")
        result = calculate_fee_by_market(
            trade_amount_usd=amount,
            tier="GENERAL",
            current_apy=Decimal("4"),
            expected_profit_usd=expected_profit,
            fixed_cost_usd=Decimal("0.27"),
        )
        assert result.should_trade is True, result.reason

    def test_残高ゼロでもファネル提案は作られる(self, db_session: Session) -> None:
        """未入金ユーザーこそファネルの主対象（docs/62「残高0でも提案が出る」）。"""
        _make_user(db_session, 603)
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=Decimal("0")):
            assert _resolve_proposal_amount(db_session, 603) > Decimal("0")

    def test_RPC取得失敗は従来どおりスキップ(self, db_session: Session) -> None:
        """残高不明のまま提案額を決めない（None と 0 を混同しないこと）。"""
        _make_user(db_session, 604)
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=None):
            assert _resolve_proposal_amount(db_session, 604) == Decimal("0")

    def test_十分な残高なら従来どおり残高ベース(self, db_session: Session) -> None:
        """ファネルは入金前だけ。既存ユーザーのサイジングを変えない。"""
        _make_user(db_session, 605)
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=Decimal("5000")):
            amount = _resolve_proposal_amount(db_session, 605)
        assert amount == Decimal("500.00")  # 5000 × 10%

    def test_実測APYではファネル額が基準額を上回る(self, db_session: Session) -> None:
        """本番で実際に起きた事故 (user 19, $100固定) の直接的な修正確認。

        実測APY 3.2648% (2026-08-08 Base mainnet) では基準額 $100 は赤字だったため、
        採算が合う額 ($109.56 = 必要額$104.35×マージン1.05) まで上がることを確認する。
        """
        _make_user(db_session, 618)
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=Decimal("0")):
            amount = _resolve_proposal_amount(db_session, 618, supply_apy_pct=Decimal("3.2648"))
        assert amount == Decimal("109.56")
        assert amount > (MIN_DEPOSIT_USD * _PROPOSAL_RATIO).quantize(Decimal("0.01"))

    def test_境界をまたいでも提案額が飛ばない(self, db_session: Session) -> None:
        """$1,000 直下(ファネル)と ちょうど(残高ベース) で提案額が一致する (APY=4% 時)。

        ファネルの必要額が基準額 ($1,000×10%=$100) を下回る APY では、
        ファネルは基準額に張り付くため境界の連続性が保たれる。別の値を使うと境界で
        提案額が不連続に飛び、ユーザーには理由の分からない金額変動として見える。
        APY が下がり必要額が基準額を上回る場合は、この連続性は意図的に崩れる
        (実際の採算ラインに合わせて必要残高そのものが上がるため。T2 の主目的)。
        """
        _make_user(db_session, 606)
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=Decimal("999.99")):
            below = _resolve_proposal_amount(db_session, 606, supply_apy_pct=Decimal("4"))
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=MIN_DEPOSIT_USD):
            at = _resolve_proposal_amount(db_session, 606, supply_apy_pct=Decimal("4"))
        assert below == at

    def test_帳簿を持つユーザーにはファネルを適用しない(self, db_session: Session) -> None:
        """★境界: allocation 帳簿 = パートナー/テスター枠。資金は入金でなく運用側の配分で入る。

        実残高が帳簿を下回るのは「本人が入金していない」のではなく「帳簿と実残高の乖離」
        であり、本人に入金を促すのは筋違い（運用側が直すべき問題）。
        PR #1035「SCW実残高が最低入金額未満なら提案を作らない」の安全性を壊さないこと。
        """
        from app.partner.allocation_models import FundAllocation

        # SCW 保有ユーザーは allocation 分岐を飛ばして wallet 経路に来る
        # (uses_custodial_allocation=False)。PR #1035 が守っている境界はここ。
        user = _make_user(db_session, 607)
        user.smart_wallet_address = "0x" + "e" * 40
        db_session.flush()
        db_session.add(
            FundAllocation(
                partner_id=1,
                tester_name="funnel-boundary",
                tester_user_id=607,
                allocated_amount_usd=Decimal("4600"),
                status="active",
            )
        )
        db_session.flush()
        with patch(f"{_SCHED}._read_wallet_usdc_balance", return_value=Decimal("50")):
            assert _resolve_proposal_amount(db_session, 607) == Decimal("0")


class TestExecutionSafety:
    """提案額 > 現残高 が正常系になるため、実行側の再検証が安全性の要になる。"""

    def _run(self, db: Session, balance: Decimal | None) -> int:
        # run_funding_detection_once は依存を**関数内 import** するため、
        # scheduled_tasks の属性ではなく import 元を差し替える必要がある。
        with (
            patch("app.database.SessionLocal", return_value=_NoCloseSession(db)),
            patch("app.aave.balance.read_wallet_usdc_balance", return_value=balance),
            patch("app.notifications.factory.get_notification_service"),
        ):
            return run_funding_detection_once()

    def test_提案額を満たしても最低入金額未満なら承認しない(self, db_session: Session) -> None:
        """★中核: 残高$150 で $100 提案を承認すると総資産の67%を1取引で supply してしまう。

        CLAUDE.md [CRITICAL] 3「Max single trade: 10% of total assets」違反。
        `balance >= amount_usd` だけを見ていた旧実装ではこれが通っていた。
        """
        _make_user(db_session, 611)
        p = _make_awaiting_proposal(db_session, 611, Decimal("100"))
        self._run(db_session, Decimal("150"))
        db_session.refresh(p)
        assert p.status == "awaiting_funds"

    def test_最低入金額に達したら承認される(self, db_session: Session) -> None:
        """$1,000 到達時、$100 の提案はちょうど総資産の 10%（ルール内）。"""
        _make_user(db_session, 612)
        p = _make_awaiting_proposal(db_session, 612, Decimal("100"))
        self._run(db_session, MIN_DEPOSIT_USD)
        db_session.refresh(p)
        assert p.status == "approved"
        assert p.approved_at is not None

    def test_最低入金額を満たしても提案額に届かなければ承認しない(
        self, db_session: Session
    ) -> None:
        """両条件の AND であることの確認（片方だけでは不十分）。"""
        _make_user(db_session, 613)
        p = _make_awaiting_proposal(db_session, 613, Decimal("5000"))
        self._run(db_session, MIN_DEPOSIT_USD)
        db_session.refresh(p)
        assert p.status == "awaiting_funds"

    def test_RPC失敗では状態を変えない(self, db_session: Session) -> None:
        """残高不明で承認すると未入金のまま実行されうる（fail-closed）。"""
        _make_user(db_session, 614)
        p = _make_awaiting_proposal(db_session, 614, Decimal("100"))
        self._run(db_session, None)
        db_session.refresh(p)
        assert p.status == "awaiting_funds"

    def test_旧実装なら承認していたはずのケースを新実装は拒否する(
        self, db_session: Session
    ) -> None:
        """★2026-08-08 (Asana 1217292389876406) の中核: 10%ルールの直接検証。

        旧実装は `balance >= amount_usd AND balance >= MIN_DEPOSIT_USD` を見ていた。
        実APY連動で提案額が $104.35 (>$1,000×10%=$100) になった場合、
        残高 $1,000 では旧式だと「1000>=104.35 かつ 1000>=1000」で**承認されてしまう**
        (104.35/1000 = 10.435% > 10%、CLAUDE.md [CRITICAL] 3 違反)。
        新実装 (amount <= balance × 10%) はこれを正しく拒否する。
        """
        _make_user(db_session, 616)
        p = _make_awaiting_proposal(db_session, 616, Decimal("104.35"))
        self._run(db_session, MIN_DEPOSIT_USD)
        db_session.refresh(p)
        assert p.status == "awaiting_funds"

    def test_10パーセント以内なら実APY連動の提案額でも承認される(self, db_session: Session) -> None:
        """残高がもう少し多ければ (10%以内に収まれば) 承認される。"""
        _make_user(db_session, 617)
        p = _make_awaiting_proposal(db_session, 617, Decimal("104.35"))
        self._run(db_session, Decimal("1050"))  # 104.35/1050 = 9.94% < 10%
        db_session.refresh(p)
        assert p.status == "approved"

    def test_入金期限を過ぎたら残高に関わらず期限切れ(self, db_session: Session) -> None:
        """funding window は市場期限と分離されているが、無期限ではない。"""
        _make_user(db_session, 615)
        p = _make_awaiting_proposal(db_session, 615, Decimal("100"))
        p.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.flush()
        self._run(db_session, MIN_DEPOSIT_USD * 10)
        db_session.refresh(p)
        assert p.status == "expired"


@pytest.fixture(autouse=True)
def _clear_deposit_gap_throttle() -> Generator[None, None, None]:
    """アラート絞り込みはプロセス内 dict なのでテスト間で持ち越さない。"""
    sched._deposit_gap_alerted_at.clear()
    yield
    sched._deposit_gap_alerted_at.clear()


class TestDepositGapNotification:
    """公表最低入金額が実際の採算ラインを下回った際の運用者通知 (Asana 1217292627294465)。

    公表額($1,000)の見直しは事業判断であり Claude では決めない。ここで検証するのは
    「判断材料 (実APY/必要残高/公表額) が自動的に運用者へ上がること」そのもの。
    """

    def test_必要残高が公表額以下なら通知しない(self) -> None:
        with patch(_FACTORY) as factory:
            _notify_deposit_gap_if_needed(
                required_balance=MIN_DEPOSIT_USD, effective_apy=Decimal("4")
            )
        factory.assert_not_called()

    def test_必要残高が公表額を超えたら通知する(self) -> None:
        with patch(_FACTORY) as factory:
            factory.return_value.send = lambda _m: None
            _notify_deposit_gap_if_needed(
                required_balance=Decimal("1043.45"), effective_apy=Decimal("3.2648")
            )
        factory.assert_called_once()

    def test_同一条件への連投は絞られる(self) -> None:
        """毎tick発火すると Slack を埋め尽くす（既存アラートの前例と同じ理由で絞る）。"""
        with patch(_FACTORY) as factory:
            factory.return_value.send = lambda _m: None
            for _ in range(3):
                _notify_deposit_gap_if_needed(
                    required_balance=Decimal("1043.45"), effective_apy=Decimal("3.2648")
                )
        assert factory.call_count == 1

    def test_絞り込み期間を過ぎれば再送される(self) -> None:
        with patch(_FACTORY) as factory:
            factory.return_value.send = lambda _m: None
            _notify_deposit_gap_if_needed(
                required_balance=Decimal("1043.45"), effective_apy=Decimal("3.2648")
            )
            sched._deposit_gap_alerted_at["global"] = datetime.now(timezone.utc) - timedelta(
                hours=sched._DEPOSIT_GAP_ALERT_INTERVAL_HOURS + 1
            )
            _notify_deposit_gap_if_needed(
                required_balance=Decimal("1043.45"), effective_apy=Decimal("3.2648")
            )
        assert factory.call_count == 2

    def test_通知送信が失敗しても例外を伝播しない(self) -> None:
        with patch(_FACTORY, side_effect=RuntimeError("slack down")):
            _notify_deposit_gap_if_needed(
                required_balance=Decimal("1043.45"), effective_apy=Decimal("3.2648")
            )  # 例外が出ないこと
