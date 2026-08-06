# Copyright (c) Ultra AutoTrade. All rights reserved.
"""deposit_policy（運用開始の最低入金額ポリシー）の単体テスト。"""

from decimal import Decimal

from app.users import deposit_policy
from app.users.deposit_policy import MIN_DEPOSIT_USD, meets_minimum_deposit


def test_min_deposit_default_is_1000() -> None:
    """env 未設定時のデフォルトは $1,000。"""
    assert MIN_DEPOSIT_USD == Decimal("1000")


def test_meets_minimum_at_exact_threshold() -> None:
    """ちょうど $1,000 はゲートを通過する（>= 判定）。"""
    assert meets_minimum_deposit(Decimal("1000")) is True


def test_below_threshold_blocked() -> None:
    """$999.99 はブロックされる。"""
    assert meets_minimum_deposit(Decimal("999.99")) is False


def test_above_threshold_passes() -> None:
    """$1,000 超は通過する。"""
    assert meets_minimum_deposit(Decimal("1500")) is True


def test_none_balance_is_safe_false() -> None:
    """残高取得不能（None）は安全側に倒して False。"""
    assert meets_minimum_deposit(None) is False


def test_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """env MIN_DEPOSIT_USD で上書きできる（モジュール再読込で反映）。"""
    import importlib

    monkeypatch.setenv("MIN_DEPOSIT_USD", "300")
    reloaded = importlib.reload(deposit_policy)
    try:
        assert reloaded.MIN_DEPOSIT_USD == Decimal("300")
        assert reloaded.meets_minimum_deposit(Decimal("250")) is False
        assert reloaded.meets_minimum_deposit(Decimal("300")) is True
    finally:
        monkeypatch.delenv("MIN_DEPOSIT_USD", raising=False)
        importlib.reload(deposit_policy)
