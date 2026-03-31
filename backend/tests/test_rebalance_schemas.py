# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_rebalance_schemas.py

"""
リバランススキーマのバリデーションテスト。

対象モジュール: app.aave.rebalance_schemas
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.aave.rebalance_schemas import (
    AssetAllocation,
    ProposedOperation,
    RebalanceExecuteRequest,
    RebalanceExecuteResponse,
    RebalanceExecutionStatus,
    RebalanceHistoryEntry,
    RebalanceProposal,
    RebalanceResult,
    RebalanceSimulateRequest,
    RebalanceSimulateResponse,
    RebalanceStatusResponse,
)
from app.aave.schemas import AaveOperationResult, AaveOperationStatus, AaveOperationType

# ==============================================================================
# Helper factories
# ==============================================================================

_NOW = datetime(2026, 3, 12, 0, 0, 0, tzinfo=timezone.utc)


def _make_asset_allocation(**kwargs) -> AssetAllocation:
    defaults = dict(
        asset_symbol="USDC",
        current_amount_usd=Decimal("1000.00"),
        current_pct=Decimal("50.00"),
        target_pct=Decimal("50.00"),
        deviation_pct=Decimal("0.00"),
    )
    defaults.update(kwargs)
    return AssetAllocation(**defaults)


def _make_proposed_operation(**kwargs) -> ProposedOperation:
    defaults = dict(
        asset_symbol="USDC",
        operation=AaveOperationType.DEPOSIT,
        amount_usd=Decimal("100.00"),
        reason="USDC is underweight",
    )
    defaults.update(kwargs)
    return ProposedOperation(**defaults)


def _make_aave_operation_result(**kwargs) -> AaveOperationResult:
    defaults = dict(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("100.00"),
        tx_hash=None,
        message=None,
        before_health_factor=None,
        after_health_factor=None,
    )
    defaults.update(kwargs)
    return AaveOperationResult(**defaults)


def _make_rebalance_proposal(**kwargs) -> RebalanceProposal:
    defaults = dict(
        proposal_id="prop-uuid-001",
        created_at=_NOW,
        health_factor_before=Decimal("2.0"),
        total_value_usd=Decimal("10000.00"),
        allocations=[_make_asset_allocation()],
        operations=[_make_proposed_operation()],
        estimated_health_factor_after=None,
        max_single_trade_pct=Decimal("10.00"),
        confirmation_token="tok-abc123",
        is_executable=True,
        rejection_reasons=[],
    )
    defaults.update(kwargs)
    return RebalanceProposal(**defaults)


def _make_rebalance_result(**kwargs) -> RebalanceResult:
    defaults = dict(
        proposal_id="prop-uuid-001",
        executed_at=_NOW,
        operations=[_make_aave_operation_result()],
        health_factor_before=Decimal("2.0"),
        health_factor_after=None,
        status=RebalanceExecutionStatus.SUCCESS,
        message=None,
    )
    defaults.update(kwargs)
    return RebalanceResult(**defaults)


def _make_rebalance_status_response(**kwargs) -> RebalanceStatusResponse:
    allocation = _make_asset_allocation()
    defaults = dict(
        current_allocations=[allocation],
        target_allocations=[allocation],
        health_factor=Decimal("2.0"),
        total_value_usd=Decimal("10000.00"),
        deviation_threshold_pct=Decimal("5.00"),
        needs_rebalance=False,
        last_rebalance_at=None,
        cooldown_remaining_seconds=0,
    )
    defaults.update(kwargs)
    return RebalanceStatusResponse(**defaults)


# ==============================================================================
# RebalanceExecutionStatus enum tests
# ==============================================================================


class TestRebalanceExecutionStatus:
    def test_all_enum_values_exist(self) -> None:
        assert RebalanceExecutionStatus.SUCCESS == "SUCCESS"
        assert RebalanceExecutionStatus.PARTIAL == "PARTIAL"
        assert RebalanceExecutionStatus.FAILED == "FAILED"
        assert RebalanceExecutionStatus.ABORTED == "ABORTED"

    def test_enum_is_str_subclass(self) -> None:
        for member in RebalanceExecutionStatus:
            assert isinstance(member, str)

    def test_enum_count(self) -> None:
        assert len(RebalanceExecutionStatus) == 4


# ==============================================================================
# AssetAllocation tests
# ==============================================================================


class TestAssetAllocation:
    def test_instantiation_with_valid_data(self) -> None:
        alloc = _make_asset_allocation()
        assert alloc.asset_symbol == "USDC"
        assert alloc.current_amount_usd == Decimal("1000.00")
        assert alloc.current_pct == Decimal("50.00")
        assert alloc.target_pct == Decimal("50.00")
        assert alloc.deviation_pct == Decimal("0.00")

    def test_decimal_fields_are_decimal_type(self) -> None:
        alloc = _make_asset_allocation()
        assert isinstance(alloc.current_amount_usd, Decimal)
        assert isinstance(alloc.current_pct, Decimal)
        assert isinstance(alloc.target_pct, Decimal)
        assert isinstance(alloc.deviation_pct, Decimal)

    def test_decimal_fields_serialize_to_string(self) -> None:
        alloc = _make_asset_allocation(
            current_amount_usd=Decimal("999.99"),
            current_pct=Decimal("33.33"),
            target_pct=Decimal("33.33"),
            deviation_pct=Decimal("-1.23"),
        )
        data = alloc.model_dump(mode="json")
        assert data["current_amount_usd"] == "999.99"
        assert data["current_pct"] == "33.33"
        assert data["target_pct"] == "33.33"
        assert data["deviation_pct"] == "-1.23"

    def test_negative_deviation_allowed(self) -> None:
        alloc = _make_asset_allocation(deviation_pct=Decimal("-5.00"))
        assert alloc.deviation_pct == Decimal("-5.00")

    def test_zero_current_amount_allowed(self) -> None:
        alloc = _make_asset_allocation(current_amount_usd=Decimal("0"))
        assert alloc.current_amount_usd == Decimal("0")

    def test_current_pct_above_100_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_asset_allocation(current_pct=Decimal("100.01"))

    def test_current_pct_below_0_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_asset_allocation(current_pct=Decimal("-0.01"))

    def test_target_pct_above_100_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_asset_allocation(target_pct=Decimal("100.01"))

    def test_negative_current_amount_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_asset_allocation(current_amount_usd=Decimal("-1"))

    def test_no_float_contamination(self) -> None:
        # float 入力は Decimal に変換されること（Pydantic の型強制）
        alloc = AssetAllocation(
            asset_symbol="WETH",
            current_amount_usd=Decimal("500"),
            current_pct=Decimal("25"),
            target_pct=Decimal("25"),
            deviation_pct=Decimal("0"),
        )
        assert isinstance(alloc.current_amount_usd, Decimal)
        assert isinstance(alloc.current_pct, Decimal)


# ==============================================================================
# ProposedOperation tests
# ==============================================================================


class TestProposedOperation:
    def test_instantiation_with_valid_data(self) -> None:
        op = _make_proposed_operation()
        assert op.asset_symbol == "USDC"
        assert op.operation is AaveOperationType.DEPOSIT
        assert op.amount_usd == Decimal("100.00")
        assert op.reason == "USDC is underweight"

    def test_decimal_field_is_decimal_type(self) -> None:
        op = _make_proposed_operation()
        assert isinstance(op.amount_usd, Decimal)

    def test_decimal_field_serializes_to_string(self) -> None:
        op = _make_proposed_operation(amount_usd=Decimal("250.75"))
        data = op.model_dump(mode="json")
        assert data["amount_usd"] == "250.75"

    def test_withdraw_operation(self) -> None:
        op = _make_proposed_operation(operation=AaveOperationType.WITHDRAW)
        assert op.operation is AaveOperationType.WITHDRAW

    def test_noop_operation(self) -> None:
        op = _make_proposed_operation(operation=AaveOperationType.NOOP, amount_usd=Decimal("0"))
        assert op.operation is AaveOperationType.NOOP

    def test_zero_amount_allowed(self) -> None:
        op = _make_proposed_operation(amount_usd=Decimal("0"))
        assert op.amount_usd == Decimal("0")

    def test_negative_amount_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_proposed_operation(amount_usd=Decimal("-1"))

    def test_no_float_contamination(self) -> None:
        op = ProposedOperation(
            asset_symbol="WETH",
            operation=AaveOperationType.DEPOSIT,
            amount_usd=Decimal("100"),
            reason="test",
        )
        assert isinstance(op.amount_usd, Decimal)


# ==============================================================================
# RebalanceProposal tests
# ==============================================================================


class TestRebalanceProposal:
    def test_instantiation_with_valid_data(self) -> None:
        proposal = _make_rebalance_proposal()
        assert proposal.proposal_id == "prop-uuid-001"
        assert proposal.health_factor_before == Decimal("2.0")
        assert proposal.total_value_usd == Decimal("10000.00")
        assert proposal.is_executable is True
        assert proposal.rejection_reasons == []

    def test_decimal_fields_are_decimal_type(self) -> None:
        proposal = _make_rebalance_proposal()
        assert isinstance(proposal.health_factor_before, Decimal)
        assert isinstance(proposal.total_value_usd, Decimal)
        assert isinstance(proposal.max_single_trade_pct, Decimal)

    def test_decimal_fields_serialize_to_string(self) -> None:
        proposal = _make_rebalance_proposal(
            health_factor_before=Decimal("1.85"),
            total_value_usd=Decimal("5000.00"),
            max_single_trade_pct=Decimal("10.00"),
        )
        data = proposal.model_dump(mode="json")
        assert data["health_factor_before"] == "1.85"
        assert data["total_value_usd"] == "5000.00"
        assert data["max_single_trade_pct"] == "10.00"

    def test_optional_estimated_health_factor_defaults_to_none(self) -> None:
        proposal = _make_rebalance_proposal()
        assert proposal.estimated_health_factor_after is None

    def test_optional_estimated_health_factor_serializes_none(self) -> None:
        proposal = _make_rebalance_proposal(estimated_health_factor_after=None)
        data = proposal.model_dump(mode="json")
        assert data["estimated_health_factor_after"] is None

    def test_optional_estimated_health_factor_with_value(self) -> None:
        proposal = _make_rebalance_proposal(estimated_health_factor_after=Decimal("2.1"))
        assert isinstance(proposal.estimated_health_factor_after, Decimal)
        data = proposal.model_dump(mode="json")
        assert data["estimated_health_factor_after"] == "2.1"

    def test_empty_operations_list(self) -> None:
        proposal = _make_rebalance_proposal(operations=[])
        assert proposal.operations == []
        assert len(proposal.operations) == 0

    def test_rejection_reasons_default_to_empty_list(self) -> None:
        # rejection_reasons を明示しないで作成
        proposal = RebalanceProposal(
            proposal_id="p-001",
            created_at=_NOW,
            health_factor_before=Decimal("2.0"),
            total_value_usd=Decimal("1000"),
            allocations=[],
            operations=[],
            max_single_trade_pct=Decimal("10"),
            confirmation_token="tok",
            is_executable=True,
        )
        assert proposal.rejection_reasons == []

    def test_rejection_reasons_with_values(self) -> None:
        reasons = ["Health factor too low", "Daily limit reached"]
        proposal = _make_rebalance_proposal(is_executable=False, rejection_reasons=reasons)
        assert proposal.rejection_reasons == reasons
        assert len(proposal.rejection_reasons) == 2

    def test_created_at_serializes_to_isoformat(self) -> None:
        proposal = _make_rebalance_proposal(created_at=_NOW)
        data = proposal.model_dump(mode="json")
        assert data["created_at"] == _NOW.isoformat()

    def test_multiple_operations(self) -> None:
        ops = [
            _make_proposed_operation(asset_symbol="USDC"),
            _make_proposed_operation(asset_symbol="WETH", operation=AaveOperationType.WITHDRAW),
        ]
        proposal = _make_rebalance_proposal(operations=ops)
        assert len(proposal.operations) == 2

    def test_negative_health_factor_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_rebalance_proposal(health_factor_before=Decimal("-0.1"))

    def test_max_single_trade_pct_above_100_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_rebalance_proposal(max_single_trade_pct=Decimal("100.01"))

    def test_no_float_contamination(self) -> None:
        proposal = _make_rebalance_proposal()
        assert isinstance(proposal.health_factor_before, Decimal)
        assert isinstance(proposal.total_value_usd, Decimal)
        assert isinstance(proposal.max_single_trade_pct, Decimal)


# ==============================================================================
# RebalanceResult tests
# ==============================================================================


class TestRebalanceResult:
    def test_instantiation_with_valid_data(self) -> None:
        result = _make_rebalance_result()
        assert result.proposal_id == "prop-uuid-001"
        assert result.status is RebalanceExecutionStatus.SUCCESS
        assert result.health_factor_before == Decimal("2.0")

    def test_decimal_fields_are_decimal_type(self) -> None:
        result = _make_rebalance_result()
        assert isinstance(result.health_factor_before, Decimal)

    def test_health_factor_before_serializes_to_string(self) -> None:
        result = _make_rebalance_result(health_factor_before=Decimal("1.95"))
        data = result.model_dump(mode="json")
        assert data["health_factor_before"] == "1.95"

    def test_health_factor_after_defaults_to_none(self) -> None:
        result = _make_rebalance_result()
        assert result.health_factor_after is None

    def test_health_factor_after_with_value(self) -> None:
        result = _make_rebalance_result(health_factor_after=Decimal("2.1"))
        assert isinstance(result.health_factor_after, Decimal)
        data = result.model_dump(mode="json")
        assert data["health_factor_after"] == "2.1"

    def test_health_factor_after_none_serializes_to_none(self) -> None:
        result = _make_rebalance_result(health_factor_after=None)
        data = result.model_dump(mode="json")
        assert data["health_factor_after"] is None

    def test_message_defaults_to_none(self) -> None:
        result = _make_rebalance_result()
        assert result.message is None

    def test_message_with_value(self) -> None:
        result = _make_rebalance_result(message="Rebalance completed successfully.")
        assert result.message == "Rebalance completed successfully."

    def test_executed_at_serializes_to_isoformat(self) -> None:
        result = _make_rebalance_result(executed_at=_NOW)
        data = result.model_dump(mode="json")
        assert data["executed_at"] == _NOW.isoformat()

    def test_all_status_values(self) -> None:
        for status in RebalanceExecutionStatus:
            result = _make_rebalance_result(status=status)
            assert result.status is status

    def test_no_float_contamination(self) -> None:
        result = _make_rebalance_result()
        assert isinstance(result.health_factor_before, Decimal)


# ==============================================================================
# RebalanceHistoryEntry tests
# ==============================================================================


class TestRebalanceHistoryEntry:
    def _make(self, **kwargs) -> RebalanceHistoryEntry:
        defaults = dict(
            proposal_id="hist-001",
            created_at=_NOW,
            executed_at=None,
            status=RebalanceExecutionStatus.SUCCESS,
            total_value_usd=Decimal("10000.00"),
            operations_count=2,
            health_factor_before=Decimal("2.0"),
            health_factor_after=None,
        )
        defaults.update(kwargs)
        return RebalanceHistoryEntry(**defaults)

    def test_instantiation_with_valid_data(self) -> None:
        entry = self._make()
        assert entry.proposal_id == "hist-001"
        assert entry.status is RebalanceExecutionStatus.SUCCESS
        assert entry.operations_count == 2

    def test_executed_at_defaults_to_none(self) -> None:
        entry = self._make()
        assert entry.executed_at is None

    def test_executed_at_optional_serializes_none(self) -> None:
        entry = self._make(executed_at=None)
        data = entry.model_dump(mode="json")
        assert data["executed_at"] is None

    def test_executed_at_with_value_serializes_isoformat(self) -> None:
        entry = self._make(executed_at=_NOW)
        data = entry.model_dump(mode="json")
        assert data["executed_at"] == _NOW.isoformat()

    def test_health_factor_after_defaults_to_none(self) -> None:
        entry = self._make()
        assert entry.health_factor_after is None

    def test_decimal_fields_are_decimal_type(self) -> None:
        entry = self._make()
        assert isinstance(entry.total_value_usd, Decimal)
        assert isinstance(entry.health_factor_before, Decimal)

    def test_decimal_fields_serialize_to_string(self) -> None:
        entry = self._make(
            total_value_usd=Decimal("9999.99"),
            health_factor_before=Decimal("1.75"),
        )
        data = entry.model_dump(mode="json")
        assert data["total_value_usd"] == "9999.99"
        assert data["health_factor_before"] == "1.75"

    def test_no_float_contamination(self) -> None:
        entry = self._make()
        assert isinstance(entry.total_value_usd, Decimal)
        assert isinstance(entry.health_factor_before, Decimal)


# ==============================================================================
# RebalanceStatusResponse tests
# ==============================================================================


class TestRebalanceStatusResponse:
    def test_needs_rebalance_false(self) -> None:
        resp = _make_rebalance_status_response(needs_rebalance=False)
        assert resp.needs_rebalance is False

    def test_needs_rebalance_true(self) -> None:
        resp = _make_rebalance_status_response(needs_rebalance=True)
        assert resp.needs_rebalance is True

    def test_decimal_fields_are_decimal_type(self) -> None:
        resp = _make_rebalance_status_response()
        assert isinstance(resp.health_factor, Decimal)
        assert isinstance(resp.total_value_usd, Decimal)
        assert isinstance(resp.deviation_threshold_pct, Decimal)

    def test_decimal_fields_serialize_to_string(self) -> None:
        resp = _make_rebalance_status_response(
            health_factor=Decimal("1.85"),
            total_value_usd=Decimal("8000.00"),
            deviation_threshold_pct=Decimal("5.00"),
        )
        data = resp.model_dump(mode="json")
        assert data["health_factor"] == "1.85"
        assert data["total_value_usd"] == "8000.00"
        assert data["deviation_threshold_pct"] == "5.00"

    def test_last_rebalance_at_defaults_to_none(self) -> None:
        resp = _make_rebalance_status_response()
        assert resp.last_rebalance_at is None

    def test_last_rebalance_at_none_serializes_to_none(self) -> None:
        resp = _make_rebalance_status_response(last_rebalance_at=None)
        data = resp.model_dump(mode="json")
        assert data["last_rebalance_at"] is None

    def test_last_rebalance_at_with_value(self) -> None:
        resp = _make_rebalance_status_response(last_rebalance_at=_NOW)
        data = resp.model_dump(mode="json")
        assert data["last_rebalance_at"] == _NOW.isoformat()

    def test_cooldown_remaining_seconds_zero(self) -> None:
        resp = _make_rebalance_status_response(cooldown_remaining_seconds=0)
        assert resp.cooldown_remaining_seconds == 0

    def test_cooldown_remaining_seconds_positive(self) -> None:
        resp = _make_rebalance_status_response(cooldown_remaining_seconds=300)
        assert resp.cooldown_remaining_seconds == 300

    def test_negative_cooldown_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_rebalance_status_response(cooldown_remaining_seconds=-1)

    def test_no_float_contamination(self) -> None:
        resp = _make_rebalance_status_response()
        assert isinstance(resp.health_factor, Decimal)
        assert isinstance(resp.total_value_usd, Decimal)
        assert isinstance(resp.deviation_threshold_pct, Decimal)

    def test_multiple_allocations(self) -> None:
        allocations = [
            _make_asset_allocation(asset_symbol="USDC", current_pct=Decimal("50")),
            _make_asset_allocation(asset_symbol="WETH", current_pct=Decimal("50")),
        ]
        resp = _make_rebalance_status_response(
            current_allocations=allocations, target_allocations=allocations
        )
        assert len(resp.current_allocations) == 2
        assert len(resp.target_allocations) == 2


# ==============================================================================
# RebalanceExecuteRequest tests
# ==============================================================================


class TestRebalanceExecuteRequest:
    def test_both_fields_required(self) -> None:
        req = RebalanceExecuteRequest(
            proposal_id="prop-001",
            confirmation_token="tok-xyz",
        )
        assert req.proposal_id == "prop-001"
        assert req.confirmation_token == "tok-xyz"

    def test_missing_proposal_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            RebalanceExecuteRequest(confirmation_token="tok-xyz")  # type: ignore[call-arg]

    def test_missing_confirmation_token_raises(self) -> None:
        with pytest.raises(ValidationError):
            RebalanceExecuteRequest(proposal_id="prop-001")  # type: ignore[call-arg]

    def test_empty_request_raises(self) -> None:
        with pytest.raises(ValidationError):
            RebalanceExecuteRequest()  # type: ignore[call-arg]

    def test_proposal_id_and_token_preserved_as_is(self) -> None:
        req = RebalanceExecuteRequest(
            proposal_id="550e8400-e29b-41d4-a716-446655440000",
            confirmation_token="eyJhbGciOiJIUzI1NiJ9",
        )
        assert req.proposal_id == "550e8400-e29b-41d4-a716-446655440000"
        assert req.confirmation_token == "eyJhbGciOiJIUzI1NiJ9"


# ==============================================================================
# RebalanceSimulateRequest tests
# ==============================================================================


class TestRebalanceSimulateRequest:
    def test_dry_run_defaults_to_true(self) -> None:
        req = RebalanceSimulateRequest()
        assert req.dry_run is True

    def test_dry_run_can_be_set_to_false(self) -> None:
        req = RebalanceSimulateRequest(dry_run=False)
        assert req.dry_run is False


# ==============================================================================
# RebalanceSimulateResponse tests
# ==============================================================================


class TestRebalanceSimulateResponse:
    def test_instantiation_with_proposal(self) -> None:
        proposal = _make_rebalance_proposal()
        resp = RebalanceSimulateResponse(proposal=proposal)
        assert resp.proposal.proposal_id == "prop-uuid-001"

    def test_proposal_field_required(self) -> None:
        with pytest.raises(ValidationError):
            RebalanceSimulateResponse()  # type: ignore[call-arg]


# ==============================================================================
# RebalanceExecuteResponse tests
# ==============================================================================


class TestRebalanceExecuteResponse:
    def test_instantiation_with_result(self) -> None:
        result = _make_rebalance_result()
        resp = RebalanceExecuteResponse(result=result)
        assert resp.result.proposal_id == "prop-uuid-001"
        assert resp.result.status is RebalanceExecutionStatus.SUCCESS

    def test_result_field_required(self) -> None:
        with pytest.raises(ValidationError):
            RebalanceExecuteResponse()  # type: ignore[call-arg]


# ==============================================================================
# Cross-model Decimal integrity tests
# ==============================================================================


class TestDecimalIntegrity:
    """全 Decimal フィールドが float に汚染されていないことを確認する。"""

    def test_asset_allocation_no_floats(self) -> None:
        alloc = _make_asset_allocation()
        for field_name in ("current_amount_usd", "current_pct", "target_pct", "deviation_pct"):
            value = getattr(alloc, field_name)
            assert isinstance(value, Decimal), f"{field_name} should be Decimal, got {type(value)}"
            assert not isinstance(value, float), f"{field_name} must not be float"

    def test_proposed_operation_no_floats(self) -> None:
        op = _make_proposed_operation()
        assert isinstance(op.amount_usd, Decimal)
        assert not isinstance(op.amount_usd, float)

    def test_rebalance_proposal_no_floats(self) -> None:
        proposal = _make_rebalance_proposal(estimated_health_factor_after=Decimal("2.1"))
        for field_name in (
            "health_factor_before",
            "total_value_usd",
            "max_single_trade_pct",
            "estimated_health_factor_after",
        ):
            value = getattr(proposal, field_name)
            assert isinstance(value, Decimal), f"{field_name} should be Decimal, got {type(value)}"
            assert not isinstance(value, float), f"{field_name} must not be float"

    def test_rebalance_result_no_floats(self) -> None:
        result = _make_rebalance_result(health_factor_after=Decimal("2.05"))
        for field_name in ("health_factor_before", "health_factor_after"):
            value = getattr(result, field_name)
            assert isinstance(value, Decimal), f"{field_name} should be Decimal, got {type(value)}"
            assert not isinstance(value, float), f"{field_name} must not be float"

    def test_rebalance_status_response_no_floats(self) -> None:
        resp = _make_rebalance_status_response()
        for field_name in ("health_factor", "total_value_usd", "deviation_threshold_pct"):
            value = getattr(resp, field_name)
            assert isinstance(value, Decimal), f"{field_name} should be Decimal, got {type(value)}"
            assert not isinstance(value, float), f"{field_name} must not be float"
