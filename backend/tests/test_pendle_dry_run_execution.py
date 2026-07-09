# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_pendle_dry_run_execution.py
"""[Phase D / D2] Pendle BUY_PT の dry-run calldata 構築 (_execute_pendle_for_proposal)。

RouterV4 Hosted SDK で swapExactTokenForPt の未署名 tx を **構築するのみ** で broadcast
しないことを保証する。構築できたら ``PendleDryRunNotBroadcast`` を送出し proposal は
'approved' 据え置き (501)。stablecoin PT (USDC 入力) のみ許可し、非 stablecoin / wallet
未設定 / BUY_PT 以外は fail-closed で拒否する (誤数量署名防止)。
"""

import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-pendle-dryrun")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.proposals.router as router_mod  # noqa: E402
import app.protocols.pendle.client as pendle_client_mod  # noqa: E402
import app.protocols.pendle.config as pendle_config_mod  # noqa: E402
from app.proposals.router import (  # noqa: E402
    PendleDryRunNotBroadcast,
    ProtocolExecutionNotWiredError,
    _execute_pendle_for_proposal,
)
from app.protocols.pendle.client import PendleBuildTxError  # noqa: E402
from app.protocols.pendle.config import PendleConfig  # noqa: E402
from app.protocols.pendle.schemas import RouterV4SwapResult  # noqa: E402

_ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"
_MARKET = "0x1111111111111111111111111111111111111111"  # yoUSD market (stub)
_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC
_WALLET = "0x7f9300000000000000000000000000000000a0Ff"


def _mk_proposal(operation: str = "BUY_PT", amount_usd: object = Decimal("100.00")) -> MagicMock:
    p = MagicMock()
    p.id = 42
    p.protocol = "pendle"
    p.operation = operation
    p.amount_usd = amount_usd
    p.user_id = 11
    return p


def _mk_db(wallet: object = _WALLET, smart: object = None) -> MagicMock:
    db = MagicMock()
    user = MagicMock()
    user.wallet_address = wallet
    user.smart_wallet_address = smart
    db.get.return_value = user
    return db


class _FakeRouterClient:
    """build_buy_pt_swap_result が呼ばれた引数を記録する async スタブ。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.raise_exc: Exception | None = None

    async def build_buy_pt_swap_result(self, **kwargs: object) -> RouterV4SwapResult:
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        return RouterV4SwapResult(
            success=True, to=_ROUTER, calldata="0x" + "ab" * 100, approvals=[]
        )


def _patch_pendle(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stable: bool = True,
    fake: _FakeRouterClient | None = None,
) -> _FakeRouterClient:
    config = PendleConfig(
        market_address=_MARKET,
        underlying_token_address=_USDC,
        underlying_token_decimals=6,
        stable_underlying=stable,
    )
    monkeypatch.setattr(pendle_config_mod, "get_pendle_config", lambda: config)
    client = fake if fake is not None else _FakeRouterClient()
    monkeypatch.setattr(pendle_client_mod, "get_pendle_router_v4_client", lambda cfg: client)
    return client


def test_dry_run_builds_calldata_and_raises_not_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUY_PT + stablecoin + wallet 設定 → calldata 構築し PendleDryRunNotBroadcast 送出。"""
    client = _patch_pendle(monkeypatch)
    with pytest.raises(PendleDryRunNotBroadcast):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())

    # build_buy_pt_tx が stablecoin (USDC=6桁) の正しい引数で 1 回だけ呼ばれた。
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["market_address"] == _MARKET
    assert call["token_in"] == _USDC
    assert call["amount_in"] == Decimal("100.00")  # amount_usd をそのまま USDC 数量に
    assert call["from_address"] == _WALLET
    assert call["token_in_decimals"] == 6  # USDC 桁ズレ防止


def test_dry_run_prefers_smart_wallet_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """SCW ユーザーは smart_wallet_address を署名者/着金先にする。"""
    client = _patch_pendle(monkeypatch)
    smart = "0xSMART00000000000000000000000000000000cafe"
    with pytest.raises(PendleDryRunNotBroadcast):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db(wallet=_WALLET, smart=smart))
    assert client.calls[0]["from_address"] == smart


def test_dry_run_is_subclass_of_not_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    """PendleDryRunNotBroadcast は ProtocolExecutionNotWiredError の subclass (501 踏襲)。"""
    _patch_pendle(monkeypatch)
    with pytest.raises(ProtocolExecutionNotWiredError):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())


def test_non_buy_pt_operation_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUY_PT 以外は SDK を呼ばず ProtocolExecutionNotWiredError で拒否。"""
    client = _patch_pendle(monkeypatch)
    with pytest.raises(ProtocolExecutionNotWiredError) as exc:
        _execute_pendle_for_proposal(_mk_proposal(operation="SUPPLY"), _mk_db())
    assert not isinstance(exc.value, PendleDryRunNotBroadcast)
    assert client.calls == []


def test_non_stable_underlying_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 stablecoin market は USD→token 換算未配線のため SDK を呼ばず拒否 (誤数量署名防止)。"""
    client = _patch_pendle(monkeypatch, stable=False)
    with pytest.raises(ProtocolExecutionNotWiredError):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())
    assert client.calls == []


def test_missing_wallet_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """wallet 未設定は未署名 tx を組めないため SDK を呼ばず拒否。"""
    client = _patch_pendle(monkeypatch)
    with pytest.raises(ProtocolExecutionNotWiredError):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db(wallet="", smart=None))
    assert client.calls == []


def test_non_positive_amount_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """amount_usd<=0 は拒否。"""
    _patch_pendle(monkeypatch)
    with pytest.raises(ProtocolExecutionNotWiredError):
        _execute_pendle_for_proposal(_mk_proposal(amount_usd=Decimal("0")), _mk_db())


def test_build_failure_raises_not_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    """calldata 取得失敗 (Router 不一致等) は握りつぶさず fail-closed で 501 相当。"""
    fake = _FakeRouterClient()
    fake.raise_exc = PendleBuildTxError("router address mismatch")
    _patch_pendle(monkeypatch, fake=fake)
    with pytest.raises(ProtocolExecutionNotWiredError) as exc:
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())
    # dry-run 成功シグナルではなく素の未配線エラー (broadcast されていない)。
    assert not isinstance(exc.value, PendleDryRunNotBroadcast)


def test_dry_run_never_calls_aave(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pendle dry-run は Aave 経路を絶対に呼ばない (誤実行防止)。"""
    _patch_pendle(monkeypatch)

    def _must_not_run(p: object, db: object) -> None:
        raise AssertionError("Pendle 提案で Aave 経路を実行してはならない")

    monkeypatch.setattr(router_mod, "_execute_aave_for_proposal", _must_not_run)
    with pytest.raises(PendleDryRunNotBroadcast):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())


@pytest.mark.parametrize(
    ("chain", "expected_chain_id"),
    [
        ("base", 8453),
        ("base_sepolia", 84532),
        ("arbitrum", 42161),
    ],
)
def test_chain_id_map_includes_base(chain: str, expected_chain_id: int) -> None:
    """RouterV4Client が Base / Base Sepolia の chainId を正しく解決する。

    map に無いと 42161 (Arbitrum) に既定化し、Base 向け calldata を Arbitrum で組む事故になる。
    """
    from app.protocols.pendle.client import PendleRouterV4Client

    config = PendleConfig(chain=chain)
    client = PendleRouterV4Client(config)
    assert client._chain_id == expected_chain_id
