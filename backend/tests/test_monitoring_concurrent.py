# backend/tests/test_monitoring_concurrent.py

"""
MonitoringService の並列ヘルスファクターチェックのユニットテスト。

python-async-patterns.md の「Pattern 8: Testing Async Code」に準拠。
"""

from decimal import Decimal
from typing import Optional

import pytest

from app.automation.monitoring_service import MonitoringService


@pytest.mark.asyncio
async def test_check_health_factors_concurrent_success():
    """複数ウォレットの並列チェックが成功することを確認。"""
    service = MonitoringService(enable_state_sync=False)

    wallet_hf_map = {
        "0xWallet1": Decimal("2.0"),
        "0xWallet2": Decimal("1.9"),
        "0xWallet3": Decimal("1.8"),
    }

    def mock_get_hf(wallet: str) -> Optional[Decimal]:
        return wallet_hf_map.get(wallet)

    wallets = list(wallet_hf_map.keys())

    results = await service.check_health_factors_concurrent(
        wallets=wallets,
        get_health_factor_func=mock_get_hf,
    )

    assert len(results) == 3
    assert results[0] == Decimal("2.0")
    assert results[1] == Decimal("1.9")
    assert results[2] == Decimal("1.8")


@pytest.mark.asyncio
async def test_check_health_factors_concurrent_empty_list():
    """空のウォレットリストで空のリストが返ることを確認。"""
    service = MonitoringService(enable_state_sync=False)

    def mock_get_hf(wallet: str) -> Optional[Decimal]:
        return Decimal("2.0")

    results = await service.check_health_factors_concurrent(
        wallets=[],
        get_health_factor_func=mock_get_hf,
    )

    assert results == []


@pytest.mark.asyncio
async def test_check_health_factors_concurrent_partial_failure():
    """一部のウォレットでエラーが発生しても継続することを確認。"""
    service = MonitoringService(enable_state_sync=False)

    def mock_get_hf(wallet: str) -> Optional[Decimal]:
        if wallet == "0xFail":
            raise RuntimeError("Simulated RPC error")
        return Decimal("2.0")

    wallets = ["0xSuccess1", "0xFail", "0xSuccess2"]

    results = await service.check_health_factors_concurrent(
        wallets=wallets,
        get_health_factor_func=mock_get_hf,
    )

    assert len(results) == 3
    assert results[0] == Decimal("2.0")
    assert results[1] is None  # エラー時は None（fail-closed）
    assert results[2] == Decimal("2.0")


@pytest.mark.asyncio
async def test_check_health_factors_concurrent_timeout():
    """タイムアウト時に None が返ることを確認。"""
    service = MonitoringService(enable_state_sync=False)

    def slow_get_hf(wallet: str) -> Optional[Decimal]:
        import time

        time.sleep(2)  # 2秒待機（タイムアウトより長い）
        return Decimal("2.0")

    results = await service.check_health_factors_concurrent(
        wallets=["0xSlow"],
        get_health_factor_func=slow_get_hf,
        timeout_seconds=0.5,  # 0.5秒でタイムアウト
    )

    assert len(results) == 1
    assert results[0] is None  # タイムアウト時は None


@pytest.mark.asyncio
async def test_check_health_factors_concurrent_respects_semaphore():
    """同時実行数が制限されることを確認。"""
    service = MonitoringService(enable_state_sync=False)

    max_concurrent_seen = 0
    current_concurrent = 0

    def mock_get_hf(wallet: str) -> Optional[Decimal]:
        nonlocal max_concurrent_seen, current_concurrent
        current_concurrent += 1
        if current_concurrent > max_concurrent_seen:
            max_concurrent_seen = current_concurrent

        import time

        time.sleep(0.05)  # 少し待機

        current_concurrent -= 1
        return Decimal("2.0")

    # 10個のウォレットを max_concurrent=3 でチェック
    wallets = [f"0xWallet{i}" for i in range(10)]

    results = await service.check_health_factors_concurrent(
        wallets=wallets,
        get_health_factor_func=mock_get_hf,
        max_concurrent=3,
    )

    assert len(results) == 10
    assert all(r == Decimal("2.0") for r in results)
    # 同時実行数は max_concurrent 以下であるはず
    assert max_concurrent_seen <= 3


@pytest.mark.asyncio
async def test_check_all_positions_safe_no_debt():
    """借入なし（HF=None）の場合に安全と判定されることを確認。"""
    service = MonitoringService(enable_state_sync=False)

    def mock_get_hf() -> Optional[Decimal]:
        return None  # 借入なし

    result = await service.check_all_positions_safe(
        get_health_factor_func=mock_get_hf,
    )

    assert result is True


@pytest.mark.asyncio
async def test_check_all_positions_safe_healthy():
    """ヘルスファクターが閾値以上の場合に安全と判定されることを確認。"""
    service = MonitoringService(enable_state_sync=False)

    def mock_get_hf() -> Optional[Decimal]:
        return Decimal("2.0")  # 安全な値

    result = await service.check_all_positions_safe(
        get_health_factor_func=mock_get_hf,
    )

    assert result is True


@pytest.mark.asyncio
async def test_check_all_positions_safe_emergency():
    """ヘルスファクターが緊急閾値未満の場合に危険と判定されることを確認。"""
    service = MonitoringService(enable_state_sync=False)

    def mock_get_hf() -> Optional[Decimal]:
        return Decimal("1.5")  # 緊急閾値（1.6）未満

    result = await service.check_all_positions_safe(
        get_health_factor_func=mock_get_hf,
    )

    assert result is False


@pytest.mark.asyncio
async def test_check_all_positions_safe_error():
    """エラー発生時に危険（False）と判定されることを確認。"""
    service = MonitoringService(enable_state_sync=False)

    def mock_get_hf() -> Optional[Decimal]:
        raise RuntimeError("Simulated error")

    result = await service.check_all_positions_safe(
        get_health_factor_func=mock_get_hf,
    )

    assert result is False  # fail-closed
