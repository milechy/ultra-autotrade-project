# backend/tests/test_automation_monitoring.py

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import AlertLevel, ComponentType


def test_latency_thresholds_warning_and_alert() -> None:
    service = MonitoringService(
        latency_warning_threshold_s=10.0,
        latency_alert_threshold_s=30.0,
    )

    # 11秒 → WARNING
    event_warning = service.record_latency(
        ComponentType.AI, timedelta(seconds=11), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert event_warning is not None
    assert event_warning.level == AlertLevel.WARNING
    assert event_warning.code == "LATENCY_WARNING"

    # 31秒 → ALERT
    event_alert = service.record_latency(
        ComponentType.AI, timedelta(seconds=31), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert event_alert is not None
    assert event_alert.level == AlertLevel.ALERT
    assert event_alert.code == "LATENCY_ALERT"


def test_health_factor_warning_and_emergency() -> None:
    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
    )

    # 1.7 → WARNING だが緊急停止にはならない
    status_warning = service.record_health_factor(
        Decimal("1.7"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert status_warning.level == AlertLevel.WARNING
    assert status_warning.is_emergency is False
    assert service.is_trading_allowed() is True

    # 1.5 → EMERGENCY で緊急停止
    status_emergency = service.record_health_factor(
        Decimal("1.5"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert status_emergency.level == AlertLevel.EMERGENCY
    assert status_emergency.is_emergency is True
    assert service.is_trading_allowed() is False

    status = service.get_status()
    assert status.is_trading_paused is True
    assert status.last_health_factor == Decimal("1.5")
    assert status.emergency_reason is not None


def test_price_change_alert() -> None:
    service = MonitoringService(price_change_alert_threshold_pct=20.0)

    # 10% 変動 → イベントなし
    event_none = service.record_price_change_24h(
        percent_change=10.0,
        at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert event_none is None

    # 25% 変動 → ALERT
    event_alert = service.record_price_change_24h(
        percent_change=25.0,
        at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert event_alert is not None
    assert event_alert.level == AlertLevel.ALERT
    assert event_alert.code == "PRICE_CHANGE_ALERT"


# ==============================================================================
# State Sync Tests (Phase 2)
# ==============================================================================


@pytest.fixture
def temp_state_file(monkeypatch):
    """一時ディレクトリに state.json を配置するフィクスチャ。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.json"
        monkeypatch.setenv("AAVE_STATE_FILE_PATH", str(state_path))
        yield state_path


def test_state_sync_disabled_does_not_write_file(temp_state_file) -> None:
    """enable_state_sync=False の場合、state.json は作成されない。"""
    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=False,
    )

    service.record_health_factor(
        Decimal("1.7"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )

    assert not temp_state_file.exists()


def test_state_sync_normal_mode(temp_state_file) -> None:
    """HF >= 1.8 の場合、NORMAL モードで state.json が作成される。"""
    from app.aave.schemas import AaveOperationMode
    from app.aave.state_manager import read_system_state

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    service.record_health_factor(
        Decimal("2.0"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )

    assert temp_state_file.exists()
    state = read_system_state()
    assert state is not None
    assert state.mode == AaveOperationMode.NORMAL
    assert state.emergency_stop is False
    assert state.health_factor == Decimal("2.0")


def test_state_sync_safe_mode(temp_state_file) -> None:
    """1.6 <= HF < 1.8 の場合、SAFE_MODE で state.json が更新される。"""
    from app.aave.schemas import AaveOperationMode
    from app.aave.state_manager import read_system_state

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    service.record_health_factor(
        Decimal("1.7"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )

    state = read_system_state()
    assert state is not None
    assert state.mode == AaveOperationMode.SAFE_MODE
    assert state.emergency_stop is False
    assert state.health_factor == Decimal("1.7")
    assert "warning" in state.reason.lower()


def test_state_sync_hard_stop(temp_state_file) -> None:
    """HF < 1.6 の場合、HARD_STOP + emergency_stop=True で更新される。"""
    from app.aave.schemas import AaveOperationMode
    from app.aave.state_manager import read_system_state

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    service.record_health_factor(
        Decimal("1.5"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )

    state = read_system_state()
    assert state is not None
    assert state.mode == AaveOperationMode.HARD_STOP
    assert state.emergency_stop is True
    assert state.health_factor == Decimal("1.5")
    assert "emergency" in state.reason.lower()


def test_state_sync_preserves_circuit_closed(temp_state_file) -> None:
    """circuit_closed は既存値が維持される。"""
    from app.aave.schemas import AaveOperationMode, AaveSystemState
    from app.aave.state_manager import read_system_state, write_system_state

    # 事前に circuit_closed=False の状態を作成
    initial_state = AaveSystemState(
        emergency_stop=False,
        mode=AaveOperationMode.NORMAL,
        health_factor=Decimal("2.0"),
        last_update=datetime(2025, 1, 1, tzinfo=timezone.utc),
        reason=None,
        circuit_closed=False,  # nginx 側で開いた状態
        stale_threshold_seconds=300,
    )
    write_system_state(initial_state)

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    # HF を更新
    service.record_health_factor(
        Decimal("1.9"), at=datetime(2025, 1, 2, tzinfo=timezone.utc)
    )

    state = read_system_state()
    assert state is not None
    assert state.circuit_closed is False  # 維持されている
    assert state.health_factor == Decimal("1.9")


def test_state_sync_mode_transition(temp_state_file) -> None:
    """NORMAL → SAFE_MODE → HARD_STOP の遷移が正しく行われる。"""
    from app.aave.schemas import AaveOperationMode
    from app.aave.state_manager import read_system_state

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    # NORMAL (HF=2.0)
    service.record_health_factor(
        Decimal("2.0"), at=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    )
    state = read_system_state()
    assert state.mode == AaveOperationMode.NORMAL

    # SAFE_MODE (HF=1.7)
    service.record_health_factor(
        Decimal("1.7"), at=datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
    )
    state = read_system_state()
    assert state.mode == AaveOperationMode.SAFE_MODE

    # HARD_STOP (HF=1.5)
    service.record_health_factor(
        Decimal("1.5"), at=datetime(2025, 1, 1, 2, 0, tzinfo=timezone.utc)
    )
    state = read_system_state()
    assert state.mode == AaveOperationMode.HARD_STOP
    assert state.emergency_stop is True


def test_manual_emergency_stop_not_overwritten_by_hf_update(temp_state_file) -> None:
    """手動設定した emergency_stop が HF 更新で上書きされないことを確認。"""
    from app.aave.schemas import AaveOperationMode, AaveSystemState
    from app.aave.state_manager import read_system_state, write_system_state

    # 初期状態を手動で emergency_stop=True に設定（オペレーターが停止）
    manual_stop = AaveSystemState(
        emergency_stop=True,  # オペレーターが手動設定
        mode=AaveOperationMode.HARD_STOP,
        health_factor=Decimal("1.9"),  # HF は良好だが停止中
        last_update=datetime(2025, 1, 1, tzinfo=timezone.utc),
        reason="Manual stop by operator",
        circuit_closed=True,
        stale_threshold_seconds=300,
    )
    write_system_state(manual_stop)

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    # HF 2.0 を記録（本来なら NORMAL になる）
    service.record_health_factor(
        Decimal("2.0"), at=datetime(2025, 1, 2, tzinfo=timezone.utc)
    )

    # emergency_stop は True のまま維持されるべき
    state = read_system_state()
    assert state.emergency_stop is True, "Manual emergency_stop should not be overwritten"
    assert state.mode == AaveOperationMode.NORMAL  # モードは HF に基づいて更新
    assert state.reason == "Manual stop by operator"  # 理由も維持


def test_clear_emergency_stop_syncs_state_file(temp_state_file) -> None:
    """clear_emergency_stop() が state.json を更新することを確認。"""
    from app.aave.schemas import AaveOperationMode
    from app.aave.state_manager import read_system_state

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    # まず HARD_STOP 状態にする
    service.record_health_factor(
        Decimal("1.5"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )

    state = read_system_state()
    assert state.emergency_stop is True
    assert state.mode == AaveOperationMode.HARD_STOP

    # 緊急停止を解除
    service.clear_emergency_stop()

    state = read_system_state()
    assert state.emergency_stop is False
    # HF がまだ 1.5 なので HARD_STOP モードは維持
    assert state.mode == AaveOperationMode.HARD_STOP
    assert state.reason is None


def test_clear_emergency_stop_with_recovered_hf(temp_state_file) -> None:
    """HF 回復後に clear_emergency_stop() すると NORMAL に戻る。"""
    from app.aave.schemas import AaveOperationMode
    from app.aave.state_manager import read_system_state

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    # HARD_STOP 状態にする
    service.record_health_factor(
        Decimal("1.5"), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert service.is_trading_allowed() is False

    # HF が回復
    service.record_health_factor(
        Decimal("2.0"), at=datetime(2025, 1, 2, tzinfo=timezone.utc)
    )

    state = read_system_state()
    # emergency_stop は OR 条件で True のまま
    assert state.emergency_stop is True
    # モードは HF に基づいて NORMAL
    assert state.mode == AaveOperationMode.NORMAL

    # オペレーターが明示的に解除
    service.clear_emergency_stop()

    state = read_system_state()
    assert state.emergency_stop is False
    assert state.mode == AaveOperationMode.NORMAL


def test_state_sync_with_hf_none(temp_state_file) -> None:
    """HF=None（借入なし）でも state.json が更新される。"""
    from app.aave.schemas import AaveOperationMode
    from app.aave.state_manager import read_system_state

    service = MonitoringService(
        healthfactor_warning_threshold=Decimal("1.8"),
        healthfactor_emergency_threshold=Decimal("1.6"),
        enable_state_sync=True,
    )

    # HF=None を記録（借入なし = ポジションなし）
    status = service.record_health_factor(
        None, at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    )

    # HealthFactorStatus の確認
    assert status.current is None
    assert status.level == AlertLevel.INFO
    assert status.is_emergency is False

    # state.json が更新されていることを確認
    state = read_system_state()
    assert state is not None
    assert state.health_factor is None  # HF=None が記録される
    assert state.mode == AaveOperationMode.NORMAL  # HF=None は NORMAL 扱い
    assert state.emergency_stop is False
    assert state.last_update == datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
