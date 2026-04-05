# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_monitoring_service_di.py
"""Tests for MonitoringService DI guard and singleton behavior."""

import warnings

import pytest

from app.automation.monitoring_service import MonitoringService
from app.automation.state import get_monitoring_service, reset_state


def test_direct_instantiation_emits_warning() -> None:
    """直接インスタンス化は UserWarning を発行する。"""
    with pytest.warns(UserWarning, match="get_monitoring_service"):
        MonitoringService()


def test_internal_instantiation_no_warning() -> None:
    """_internal=True の場合は警告を発行しない。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        # Should not raise
        svc = MonitoringService(_internal=True)
    assert svc is not None


def test_get_monitoring_service_returns_singleton() -> None:
    """get_monitoring_service() は同一インスタンスを返す。"""
    reset_state()
    try:
        svc1 = get_monitoring_service()
        svc2 = get_monitoring_service()
        assert svc1 is svc2
    finally:
        reset_state()


def test_get_monitoring_service_no_warning() -> None:
    """get_monitoring_service() は警告を発行しない。"""
    reset_state()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            get_monitoring_service()  # Should not raise
    finally:
        reset_state()
