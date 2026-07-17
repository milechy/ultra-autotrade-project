# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_total_assets_resolver.py
"""`resolve_user_total_assets_usd` — risk_limiter の % 判定の分母。

CLAUDE.md Rule 3/4（単一10% / 日次30%・ABSOLUTE）は全呼び出し元が `total_assets_usd=None` を
渡しているため実際には効いていない。本 resolver がその分母を供給する（2026-07-17）。

**本テストの主眼は「判定不能を 0 にしないこと」**。0 を返すと `total_assets_usd > 0` のガードを
抜けて % 判定がスキップされる（＝黙って上限が外れる）。一方 None は「スキップ」という
既存契約どおりの扱いになり、PolicyEngine の絶対額上限に委ねられる。
"""

import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-total-assets")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.users.total_assets_resolver import (  # noqa: E402
    _read_aave_net_usd,
    resolve_user_total_assets_usd,
)

_WALLET = "0x" + "ab" * 20
_SCW = "0x" + "cd" * 20


def _account(collateral: str, debt: str) -> SimpleNamespace:
    return SimpleNamespace(
        total_collateral_usd=Decimal(collateral),
        total_debt_usd=Decimal(debt),
    )


class _FakeDb:
    """`db.get(User, user_id)` だけを模す最小 stub。"""

    def __init__(self, user: object) -> None:
        self._user = user

    def get(self, _model: object, _pk: int) -> object:
        return self._user


def _user(*, wallet: str | None = _WALLET, scw: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(wallet_address=wallet, smart_wallet_address=scw)


class TestResolveTotalAssets:
    def test_sums_aave_net_and_wallet_usdc(self) -> None:
        """総資産 = Aave net(担保-負債) + wallet USDC。"""
        db = _FakeDb(_user())
        with (
            patch(
                "app.users.total_assets_resolver._read_aave_net_usd",
                return_value=Decimal("1000"),
            ),
            patch("app.aave.balance.read_wallet_usdc_balance", return_value=Decimal("250.5")),
        ):
            assert resolve_user_total_assets_usd(db, 1) == Decimal("1250.5")

    def test_smart_wallet_takes_precedence(self) -> None:
        """SCW があれば SCW を見る（執行経路の wallet 優先順と一致させる）。"""
        db = _FakeDb(_user(wallet=_WALLET, scw=_SCW))
        seen: list[str] = []

        def _fake_net(wallet: str) -> Decimal:
            seen.append(wallet)
            return Decimal("10")

        with (
            patch("app.users.total_assets_resolver._read_aave_net_usd", side_effect=_fake_net),
            patch("app.aave.balance.read_wallet_usdc_balance", return_value=Decimal("0")),
        ):
            resolve_user_total_assets_usd(db, 1)
        assert seen == [_SCW]

    def test_no_wallet_is_undeterminable(self) -> None:
        """wallet 未設定 → None（0 ではない）。"""
        db = _FakeDb(_user(wallet=None, scw=None))
        assert resolve_user_total_assets_usd(db, 1) is None

    def test_missing_user_is_undeterminable(self) -> None:
        db = _FakeDb(None)
        assert resolve_user_total_assets_usd(db, 999) is None

    def test_aave_failure_is_none_not_zero(self) -> None:
        """★Aave 取得失敗 → None。**0 にしてはならない**。

        0 だと `total_assets_usd > 0` を抜けて % 判定が黙ってスキップされる。
        None なら既存契約どおり「スキップ + PolicyEngine 絶対額に委ねる」になる。
        """
        db = _FakeDb(_user())
        with patch("app.users.total_assets_resolver._read_aave_net_usd", return_value=None):
            result = resolve_user_total_assets_usd(db, 1)
        assert result is None
        assert result != Decimal("0")

    def test_wallet_usdc_failure_is_none_not_partial(self) -> None:
        """★wallet USDC 取得失敗 → None。

        「Aave 分だけ」で確定させると分母を過小評価し不当なブロックを生む。
        """
        db = _FakeDb(_user())
        with (
            patch(
                "app.users.total_assets_resolver._read_aave_net_usd",
                return_value=Decimal("1000"),
            ),
            patch("app.aave.balance.read_wallet_usdc_balance", return_value=None),
        ):
            assert resolve_user_total_assets_usd(db, 1) is None


class TestReadAaveNetUsd:
    def test_net_is_collateral_minus_debt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AAVE_CLIENT_TYPE", "dummy")
        with patch(
            "app.aave.client.DummyAaveClient.get_account_data",
            return_value=_account("1000", "300"),
        ):
            assert _read_aave_net_usd(_WALLET) == Decimal("700")

    def test_negative_net_clamps_to_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """負債 > 担保（清算間際）→ 0 にクランプ。

        負値を返すと `> 0` ガードを抜けて % 判定がスキップされ、**最も危険な状態で上限が外れる**。
        """
        monkeypatch.setenv("AAVE_CLIENT_TYPE", "dummy")
        with patch(
            "app.aave.client.DummyAaveClient.get_account_data",
            return_value=_account("100", "150"),
        ):
            assert _read_aave_net_usd(_WALLET) == Decimal("0")

    def test_rpc_exception_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """★RPC 例外 → None（0 にしない）。RPC 瞬断を取引停止にしないため。"""
        monkeypatch.setenv("AAVE_CLIENT_TYPE", "dummy")
        with patch(
            "app.aave.client.DummyAaveClient.get_account_data",
            side_effect=RuntimeError("rpc down"),
        ):
            assert _read_aave_net_usd(_WALLET) is None

    def test_web3_missing_env_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AAVE_CLIENT_TYPE", "web3")
        monkeypatch.delenv("AAVE_RPC_URL", raising=False)
        monkeypatch.delenv("AAVE_POOL_ADDRESS", raising=False)
        assert _read_aave_net_usd(_WALLET) is None

    def test_unknown_client_type_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AAVE_CLIENT_TYPE", "bogus")
        assert _read_aave_net_usd(_WALLET) is None
