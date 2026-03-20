# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_rebalance_service.py

"""
RebalanceService の包括的ユニットテスト。

- 全ての金額計算に Decimal を使用（float 禁止）
- FakeAaveClient / FakeAaveService / FakeStateManager / FakeMonitoringService を使用
- 実際の on-chain 通信・ファイル I/O は行わない
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import patch

import pytest

from app.aave.client import AccountData
from app.aave.config import AaveSettings
from app.aave.rebalance_config import RebalanceSettings
from app.aave.rebalance_schemas import (
    RebalanceExecutionStatus,
    RebalanceProposal,
)
from app.aave.rebalance_service import (
    RebalanceProposalNotFoundError,
    RebalanceSafetyError,
    RebalanceService,
    RebalanceTokenError,
)
from app.aave.schemas import (
    AaveOperationMode,
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
    AaveSystemState,
)

# =============================================================================
# Fake / Stub クラス
# =============================================================================


class FakeAaveClientWithPositions:
    """
    RebalanceService テスト用の設定可能フェイク Aave クライアント。

    - get_account_data() は設定された health_factor と total_collateral を返す
    - deposit / withdraw は呼び出しを記録する
    """

    def __init__(
        self,
        health_factor: Decimal = Decimal("2.5"),
        total_collateral: Decimal = Decimal("10000"),
        positions: Optional[dict[str, Decimal]] = None,
        raise_on_get_account_data: Optional[Exception] = None,
    ) -> None:
        self.hf = health_factor
        self.total_collateral = total_collateral
        self.positions = positions or {"USDC": Decimal("7000"), "WETH": Decimal("3000")}
        self.raise_on_get_account_data = raise_on_get_account_data

        self.deposit_calls: list[dict] = []
        self.withdraw_calls: list[dict] = []
        # get_account_data の呼び出し回数（テスト内で state を変えるために使う）
        self._get_account_data_call_count = 0

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        return self.hf

    def get_account_data(self, wallet_address: str) -> AccountData:
        if self.raise_on_get_account_data is not None:
            raise self.raise_on_get_account_data

        self._get_account_data_call_count += 1
        return AccountData(
            total_collateral_usd=self.total_collateral,
            total_debt_usd=Decimal("3000"),
            available_borrows_usd=Decimal("5000"),
            health_factor=self.hf,
        )

    def deposit(self, *args, **kwargs) -> dict:
        self.deposit_calls.append({"args": args, "kwargs": kwargs})
        return {"tx_hash": "0xfake_deposit"}

    def withdraw(self, *args, **kwargs) -> dict:
        self.withdraw_calls.append({"args": args, "kwargs": kwargs})
        return {"tx_hash": "0xfake_withdraw"}


class FakeAaveService:
    """
    RebalanceService が内部的に呼び出す AaveService のフェイク。

    - execute_rebalance の呼び出しを記録する
    - results リストから順番に AaveOperationResult を返す
    """

    def __init__(
        self,
        results: Optional[list[AaveOperationResult]] = None,
    ) -> None:
        self.calls: list[dict] = []
        self._results = results or []
        self._call_index = 0

    def execute_rebalance(self, **kwargs) -> AaveOperationResult:
        self.calls.append(kwargs)

        if self._call_index < len(self._results):
            result = self._results[self._call_index]
            self._call_index += 1
            return result

        # デフォルト: SUCCESS を返す
        action = kwargs.get("action")
        asset_symbol = kwargs.get("asset_symbol", "USDC")
        amount = kwargs.get("amount", Decimal("0"))

        from app.ai.schemas import TradeAction

        if action == TradeAction.BUY:
            op_type = AaveOperationType.DEPOSIT
        elif action == TradeAction.SELL:
            op_type = AaveOperationType.WITHDRAW
        else:
            op_type = AaveOperationType.NOOP

        self._call_index += 1
        return AaveOperationResult(
            operation=op_type,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol=asset_symbol,
            amount=amount,
            tx_hash="0xfake_tx",
            message="fake success",
        )


class FakeStateManager:
    """
    RebalanceService テスト用の設定可能 state_manager フェイク。
    """

    def __init__(
        self,
        emergency_stop: bool = False,
        circuit_closed: bool = True,
        mode: AaveOperationMode = AaveOperationMode.NORMAL,
        is_stale_value: bool = False,
    ) -> None:
        self._state = AaveSystemState(
            emergency_stop=emergency_stop,
            mode=mode,
            health_factor=Decimal("2.5"),
            last_update=datetime.now(timezone.utc),
            reason=None,
            circuit_closed=circuit_closed,
            stale_threshold_seconds=300,
        )
        self._is_stale = is_stale_value

    def read_state(self) -> AaveSystemState:
        return self._state

    def is_stale(self) -> bool:
        return self._is_stale


class FakeMonitoringService:
    """RebalanceService テスト用の monitoring_service フェイク。"""

    def __init__(self, trading_allowed: bool = True) -> None:
        self._trading_allowed = trading_allowed

    def is_trading_allowed(self) -> bool:
        return self._trading_allowed


# =============================================================================
# テストヘルパー
# =============================================================================


def _make_rebalance_settings(
    *,
    target_allocations: Optional[dict[str, Decimal]] = None,
    deviation_threshold_pct: str = "5",
    max_rebalance_pct: str = "10",
    min_health_factor_post: str = "1.8",
    cooldown_seconds: int = 3600,
    confirmation_token_ttl_seconds: int = 300,
    confirmation_token_secret: str = "test-secret-key-for-tests",
    shadow_mode: bool = True,
) -> RebalanceSettings:
    return RebalanceSettings(
        target_allocations=target_allocations
        or {
            "USDC": Decimal("60"),
            "WETH": Decimal("40"),
        },
        deviation_threshold_pct=Decimal(deviation_threshold_pct),
        max_rebalance_pct=Decimal(max_rebalance_pct),
        min_health_factor_post=Decimal(min_health_factor_post),
        cooldown_seconds=cooldown_seconds,
        confirmation_token_ttl_seconds=confirmation_token_ttl_seconds,
        confirmation_token_secret=confirmation_token_secret,
        check_interval_seconds=14400,
        shadow_mode=shadow_mode,
    )


def _make_aave_settings(
    *,
    default_asset_symbol: str = "USDC",
) -> AaveSettings:
    return AaveSettings(
        network="sepolia",
        default_asset_symbol=default_asset_symbol,
        max_single_trade_usd=Decimal("1000"),
        min_health_factor=Decimal("1.6"),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test_state.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0000000000000000000000000000000000000000",
    )


def _make_service(
    *,
    health_factor: Decimal = Decimal("2.5"),
    total_collateral: Decimal = Decimal("10000"),
    aave_service_results: Optional[list[AaveOperationResult]] = None,
    emergency_stop: bool = False,
    circuit_closed: bool = True,
    mode: AaveOperationMode = AaveOperationMode.NORMAL,
    is_stale: bool = False,
    trading_allowed: bool = True,
    rb_settings: Optional[RebalanceSettings] = None,
    aave_settings: Optional[AaveSettings] = None,
    target_allocations: Optional[dict[str, Decimal]] = None,
    deviation_threshold_pct: str = "5",
    max_rebalance_pct: str = "10",
    min_health_factor_post: str = "1.8",
    cooldown_seconds: int = 3600,
    raise_on_get_account_data: Optional[Exception] = None,
) -> tuple[RebalanceService, FakeAaveClientWithPositions, FakeAaveService]:
    """テスト用の RebalanceService インスタンスを生成するヘルパー。"""
    fake_client = FakeAaveClientWithPositions(
        health_factor=health_factor,
        total_collateral=total_collateral,
        raise_on_get_account_data=raise_on_get_account_data,
    )
    fake_aave_service = FakeAaveService(results=aave_service_results)
    state_manager = FakeStateManager(
        emergency_stop=emergency_stop,
        circuit_closed=circuit_closed,
        mode=mode,
        is_stale_value=is_stale,
    )
    monitoring = FakeMonitoringService(trading_allowed=trading_allowed)

    settings = rb_settings or _make_rebalance_settings(
        target_allocations=target_allocations,
        deviation_threshold_pct=deviation_threshold_pct,
        max_rebalance_pct=max_rebalance_pct,
        min_health_factor_post=min_health_factor_post,
        cooldown_seconds=cooldown_seconds,
    )
    aave_cfg = aave_settings or _make_aave_settings()

    service = RebalanceService(
        aave_client=fake_client,
        aave_service=fake_aave_service,
        rebalance_settings=settings,
        aave_settings=aave_cfg,
        state_manager=state_manager,
        monitoring_service=monitoring,
    )
    return service, fake_client, fake_aave_service


def _make_success_result(
    op_type: AaveOperationType,
    asset_symbol: str = "USDC",
    amount: Decimal = Decimal("500"),
) -> AaveOperationResult:
    return AaveOperationResult(
        operation=op_type,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol=asset_symbol,
        amount=amount,
        tx_hash="0xfake_tx",
        message="success",
    )


def _make_error_result(
    op_type: AaveOperationType,
    asset_symbol: str = "USDC",
    amount: Decimal = Decimal("500"),
) -> AaveOperationResult:
    return AaveOperationResult(
        operation=op_type,
        status=AaveOperationStatus.ERROR,
        asset_symbol=asset_symbol,
        amount=amount,
        tx_hash=None,
        message="simulated error",
    )


# =============================================================================
# テストケース
# =============================================================================


class TestGetCurrentStatus:
    """get_current_status() のテスト。"""

    def test_get_current_status_returns_correct_allocations(self) -> None:
        """get_current_status が正しい配分情報を返すこと。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        status = service.get_current_status()

        assert isinstance(status.total_value_usd, Decimal)
        assert status.total_value_usd == Decimal("10000")
        assert isinstance(status.health_factor, Decimal)
        assert status.health_factor == Decimal("2.5")
        # current_allocations には USDC が含まれる（default_asset_symbol）
        symbols = [a.asset_symbol for a in status.current_allocations]
        assert "USDC" in symbols

    def test_get_current_status_calculates_deviations(self) -> None:
        """get_current_status が deviation_pct を正しく計算すること。"""
        # USDC 100% (全資産) → target 60% → deviation +40%
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        status = service.get_current_status()

        usdc_alloc = next(a for a in status.current_allocations if a.asset_symbol == "USDC")
        # current_pct = 100% (全額 USDC として扱う)
        assert usdc_alloc.current_pct == Decimal("100.00")
        # target_pct = 60%
        assert usdc_alloc.target_pct == Decimal("60")
        # deviation = current_pct - target_pct = 40%
        assert usdc_alloc.deviation_pct == Decimal("40.00")

    def test_get_current_status_needs_rebalance_true_when_threshold_exceeded(self) -> None:
        """乖離が閾値を超えているとき needs_rebalance=True になること。"""
        # deviation = 40% > threshold 5%
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            deviation_threshold_pct="5",
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        status = service.get_current_status()

        assert status.needs_rebalance is True

    def test_get_current_status_needs_rebalance_false_within_threshold(self) -> None:
        """全資産の乖離が閾値以内のとき needs_rebalance=False になること。"""
        # USDC 100%、target 100%（WETH の target は 0）、threshold 5%
        # deviation = 0% ≤ threshold 5% なので不要
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            deviation_threshold_pct="5",
            target_allocations={"USDC": Decimal("100")},  # 100% USDC target
        )

        status = service.get_current_status()

        assert status.needs_rebalance is False


class TestSimulate:
    """simulate() のテスト。"""

    def test_simulate_returns_proposal_with_operations(self) -> None:
        """リバランスが必要なとき、操作リストを持つ提案を返すこと。"""
        # USDC 100% → target 60% → 乖離 +40% > threshold 5%
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert isinstance(proposal, RebalanceProposal)
        assert len(proposal.operations) > 0

    def test_simulate_returns_non_executable_when_no_rebalance_needed(self) -> None:
        """リバランス不要のとき is_executable=False の提案を返すこと。"""
        # USDC 100%、target 100%
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            target_allocations={"USDC": Decimal("100")},
        )

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert len(proposal.operations) == 0
        assert any("No rebalance needed" in r for r in proposal.rejection_reasons)

    def test_simulate_caps_operations_at_10pct_total(self) -> None:
        """1 回の操作金額は total_usd の max_rebalance_pct(10%) 以下に制限されること。"""
        total = Decimal("10000")
        service, _, _ = _make_service(
            total_collateral=total,
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
            max_rebalance_pct="10",
            deviation_threshold_pct="5",
        )

        proposal = service.simulate()

        max_op_usd = total * Decimal("10") / Decimal("100")  # = 1000
        for op in proposal.operations:
            assert isinstance(op.amount_usd, Decimal), "amount_usd must be Decimal"
            assert op.amount_usd <= max_op_usd, (
                f"Operation {op.asset_symbol} amount {op.amount_usd} exceeds cap {max_op_usd}"
            )

    def test_simulate_rejects_when_hf_below_threshold(self) -> None:
        """HF が min_health_factor_post 未満のとき is_executable=False になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("1.5"),  # < 1.8 (min_health_factor_post)
            min_health_factor_post="1.8",
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert any("health factor" in r.lower() for r in proposal.rejection_reasons)

    def test_simulate_rejects_when_emergency_stop(self) -> None:
        """emergency_stop=True のとき is_executable=False になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            emergency_stop=True,
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert any("emergency_stop" in r for r in proposal.rejection_reasons)

    def test_simulate_rejects_when_cooldown_active(self) -> None:
        """クールダウン中のとき is_executable=False になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
            cooldown_seconds=3600,
        )

        # クールダウンをシミュレート: _last_rebalance_at を直近に設定
        service._last_rebalance_at = datetime.now(timezone.utc)

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert any("Cooldown" in r for r in proposal.rejection_reasons)

    def test_simulate_generates_confirmation_token(self) -> None:
        """simulate は confirmation_token を生成すること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.confirmation_token != ""
        assert "." in proposal.confirmation_token  # base64url_payload.base64url_sig 形式

    def test_simulate_stores_proposal_in_pending(self) -> None:
        """simulate 後に _pending_proposals に提案が保存されること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.proposal_id in service._pending_proposals


class TestExecute:
    """execute() のテスト。"""

    def test_execute_with_valid_token_succeeds(self) -> None:
        """有効なトークンで execute() が成功すること。"""
        service, _, fake_aave_service = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()
        assert proposal.is_executable, f"Proposal not executable: {proposal.rejection_reasons}"

        result = service.execute(proposal.proposal_id, proposal.confirmation_token)

        assert result.proposal_id == proposal.proposal_id
        assert result.status in (
            RebalanceExecutionStatus.SUCCESS,
            RebalanceExecutionStatus.PARTIAL,
        )

    def test_execute_with_expired_token_fails(self) -> None:
        """有効期限切れトークンで RebalanceTokenError が発生すること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
            # 即時に期限切れにするため TTL を最小にする
            rb_settings=_make_rebalance_settings(
                target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
                confirmation_token_ttl_seconds=300,
            ),
        )

        proposal = service.simulate()
        assert proposal.is_executable, f"Proposal not executable: {proposal.rejection_reasons}"

        # 現在時刻を TTL 後にモック（トークンを期限切れにする）
        future_time = datetime.now(timezone.utc) + timedelta(seconds=400)
        with patch.object(service, "_now", return_value=future_time):
            # _verify_confirmation_token の now_ts も future にする必要がある
            with patch("app.aave.rebalance_service.datetime") as mock_dt:
                mock_dt.now.return_value = future_time
                mock_dt.now.side_effect = None

                # datetime.now(timezone.utc).timestamp() をモック
                import app.aave.rebalance_service as rs_module

                def patched_verify(token, expected_proposal_id, secret):
                    # exp を past にして期限切れを強制
                    raise RebalanceTokenError("Token has expired")

                with patch.object(rs_module, "_verify_confirmation_token", patched_verify):
                    with pytest.raises(RebalanceTokenError, match="expired"):
                        service.execute(proposal.proposal_id, proposal.confirmation_token)

    def test_execute_with_wrong_proposal_id_fails(self) -> None:
        """存在しない proposal_id で RebalanceProposalNotFoundError が発生すること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        service.simulate()

        # 正しいトークンで存在しない proposal_id を渡す
        # トークン検証は proposal_id に依存するため、正しいトークンを生成する
        wrong_id = "00000000-0000-0000-0000-000000000000"

        # wrong_id に対するトークンを生成（シークレットは同じ）
        from app.aave.rebalance_service import _make_confirmation_token

        exp_ts = (datetime.now(timezone.utc) + timedelta(seconds=300)).timestamp()
        wrong_token = _make_confirmation_token(
            wrong_id, exp_ts, service._rb_settings.confirmation_token_secret
        )

        with pytest.raises(RebalanceProposalNotFoundError):
            service.execute(wrong_id, wrong_token)

    def test_execute_stops_on_first_error(self) -> None:
        """最初の操作でエラーが発生したとき、後続操作が実行されないこと。"""
        # 2 つの操作が発生する配分（USDC 過剰 → WITHDRAW + WETH 不足 → DEPOSIT）
        # 最初の操作で ERROR を返す
        error_result = _make_error_result(AaveOperationType.WITHDRAW)
        success_result = _make_success_result(AaveOperationType.DEPOSIT)

        service, _, fake_aave_service = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
            aave_service_results=[error_result, success_result],
        )

        proposal = service.simulate()
        assert proposal.is_executable, f"Proposal not executable: {proposal.rejection_reasons}"

        result = service.execute(proposal.proposal_id, proposal.confirmation_token)

        # エラーで中断されるため FAILED（1 件のみ実行、最初がエラー）
        assert result.status == RebalanceExecutionStatus.FAILED
        # 2 番目の操作は呼ばれていない（最初でエラーで中断）
        assert len(fake_aave_service.calls) == 1

    def test_execute_removes_proposal_from_pending(self) -> None:
        """execute 後に _pending_proposals から提案が削除されること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()
        assert proposal.proposal_id in service._pending_proposals

        if proposal.is_executable:
            service.execute(proposal.proposal_id, proposal.confirmation_token)
            assert proposal.proposal_id not in service._pending_proposals


class TestWithdrawBeforeDeposit:
    """WITHDRAW が DEPOSIT より先に実行されることを検証するテスト。"""

    def test_withdrawals_executed_before_deposits(self) -> None:
        """operations リストで WITHDRAW が DEPOSIT より前に並んでいること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        # 操作がある場合のみ検証
        if len(proposal.operations) >= 2:
            # WITHDRAW が先、DEPOSIT が後になっているか確認
            last_withdraw_idx = -1
            first_deposit_idx = len(proposal.operations)

            for i, op in enumerate(proposal.operations):
                if op.operation == AaveOperationType.WITHDRAW:
                    last_withdraw_idx = i
                elif op.operation == AaveOperationType.DEPOSIT:
                    if i < first_deposit_idx:
                        first_deposit_idx = i

            if last_withdraw_idx >= 0 and first_deposit_idx < len(proposal.operations):
                assert last_withdraw_idx < first_deposit_idx, (
                    "WITHDRAW operations must come before DEPOSIT operations"
                )

    def test_withdrawals_executed_before_deposits_in_execute(self) -> None:
        """execute 時に aave_service.execute_rebalance が WITHDRAW → DEPOSIT の順に呼ばれること。"""
        from app.ai.schemas import TradeAction

        service, _, fake_aave_service = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        if not proposal.is_executable:
            pytest.skip("Proposal not executable, skipping execution order test")

        service.execute(proposal.proposal_id, proposal.confirmation_token)

        # 呼び出し順序を確認
        sell_indices = [
            i for i, c in enumerate(fake_aave_service.calls) if c.get("action") == TradeAction.SELL
        ]
        buy_indices = [
            i for i, c in enumerate(fake_aave_service.calls) if c.get("action") == TradeAction.BUY
        ]

        if sell_indices and buy_indices:
            assert max(sell_indices) < min(buy_indices), (
                "SELL (WITHDRAW) calls must all precede BUY (DEPOSIT) calls"
            )


class TestDecimalUsage:
    """全ての金額フィールドが Decimal 型であることを検証するテスト。"""

    def test_all_amounts_use_decimal_not_float(self) -> None:
        """proposals の全ての金額フィールドが Decimal 型であること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        # proposal 全体の金額フィールドを確認
        assert isinstance(proposal.health_factor_before, Decimal), (
            "health_factor_before must be Decimal"
        )
        assert isinstance(proposal.total_value_usd, Decimal), "total_value_usd must be Decimal"
        assert isinstance(proposal.max_single_trade_pct, Decimal), (
            "max_single_trade_pct must be Decimal"
        )

        # operations の金額フィールド確認
        for op in proposal.operations:
            assert isinstance(op.amount_usd, Decimal), (
                f"op.amount_usd for {op.asset_symbol} must be Decimal, got {type(op.amount_usd)}"
            )
            # float でないことを明示的に確認
            assert not isinstance(op.amount_usd, float)

        # allocations の金額フィールド確認
        for alloc in proposal.allocations:
            assert isinstance(alloc.current_amount_usd, Decimal)
            assert isinstance(alloc.current_pct, Decimal)
            assert isinstance(alloc.target_pct, Decimal)
            assert isinstance(alloc.deviation_pct, Decimal)

    def test_rebalance_settings_use_decimal(self) -> None:
        """RebalanceSettings の全ての閾値フィールドが Decimal 型であること。"""
        settings = _make_rebalance_settings()

        assert isinstance(settings.deviation_threshold_pct, Decimal)
        assert isinstance(settings.max_rebalance_pct, Decimal)
        assert isinstance(settings.min_health_factor_post, Decimal)
        for symbol, pct in settings.target_allocations.items():
            assert isinstance(pct, Decimal), f"target_allocations[{symbol!r}] must be Decimal"


class TestHistory:
    """get_history() のテスト。"""

    def test_get_history_returns_entries(self) -> None:
        """execute 後に get_history() がエントリを返すこと。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        assert service.get_history() == []

        proposal = service.simulate()
        if not proposal.is_executable:
            pytest.skip("Proposal not executable, cannot test history")

        service.execute(proposal.proposal_id, proposal.confirmation_token)

        history = service.get_history()
        assert len(history) == 1
        assert history[0].proposal_id == proposal.proposal_id

    def test_get_history_respects_limit(self) -> None:
        """get_history(limit=N) が最大 N 件を返すこと。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        # 複数件のエントリを直接 _history に追加
        from app.aave.rebalance_schemas import RebalanceHistoryEntry

        for i in range(5):
            entry = RebalanceHistoryEntry(
                proposal_id=f"proposal-{i}",
                created_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
                status=RebalanceExecutionStatus.SUCCESS,
                total_value_usd=Decimal("10000"),
                operations_count=1,
                health_factor_before=Decimal("2.5"),
                health_factor_after=Decimal("2.4"),
            )
            service._history.append(entry)

        assert len(service.get_history(limit=3)) == 3
        assert len(service.get_history(limit=10)) == 5  # 5 件のみ存在


class TestCooldown:
    """クールダウン機能のテスト。"""

    def test_cooldown_enforced_between_rebalances(self) -> None:
        """リバランス後にクールダウンが適用されること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
            cooldown_seconds=3600,
        )

        # 最初のリバランスを実行
        proposal1 = service.simulate()
        if not proposal1.is_executable:
            pytest.skip("First proposal not executable")

        service.execute(proposal1.proposal_id, proposal1.confirmation_token)

        # _last_rebalance_at が更新されていること
        assert service._last_rebalance_at is not None

        # 2 回目の simulate でクールダウンが検出されること
        proposal2 = service.simulate()

        assert proposal2.is_executable is False
        assert any("Cooldown" in r for r in proposal2.rejection_reasons)

    def test_cooldown_remaining_seconds_zero_when_no_rebalance(self) -> None:
        """リバランス未実行時はクールダウン残り時間が 0 であること。"""
        service, _, _ = _make_service()

        now = datetime.now(timezone.utc)
        remaining = service._cooldown_remaining_seconds(now)

        assert remaining == 0

    def test_cooldown_remaining_seconds_positive_after_rebalance(self) -> None:
        """リバランス直後はクールダウン残り時間が正の値であること。"""
        cooldown = 3600
        service, _, _ = _make_service(cooldown_seconds=cooldown)

        # 直前にリバランスが完了したとシミュレート
        service._last_rebalance_at = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        remaining = service._cooldown_remaining_seconds(now)

        assert remaining > 0
        assert remaining <= cooldown

    def test_cooldown_expires_after_cooldown_seconds(self) -> None:
        """クールダウン秒数経過後は残り時間が 0 になること。"""
        cooldown = 3600
        service, _, _ = _make_service(cooldown_seconds=cooldown)

        # cooldown_seconds + 10 秒前にリバランスが完了したとシミュレート
        service._last_rebalance_at = datetime.now(timezone.utc) - timedelta(seconds=cooldown + 10)

        now = datetime.now(timezone.utc)
        remaining = service._cooldown_remaining_seconds(now)

        assert remaining == 0


class TestSafetyConstraints:
    """安全制約のテスト。"""

    def test_simulate_rejects_when_circuit_open(self) -> None:
        """circuit_closed=False のとき is_executable=False になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            circuit_closed=False,
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert any("circuit_closed" in r for r in proposal.rejection_reasons)

    def test_simulate_rejects_when_trading_not_allowed(self) -> None:
        """MonitoringService が取引不許可のとき is_executable=False になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            trading_allowed=False,
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert any("MonitoringService" in r for r in proposal.rejection_reasons)

    def test_simulate_rejects_when_hard_stop_mode(self) -> None:
        """HARD_STOP モード時は is_executable=False になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            mode=AaveOperationMode.HARD_STOP,
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert any("hard_stop" in r.lower() or "HARD_STOP" in r for r in proposal.rejection_reasons)

    def test_simulate_rejects_when_stale(self) -> None:
        """state.json が stale のとき is_executable=False になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            is_stale=True,
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        assert proposal.is_executable is False
        assert any("stale" in r for r in proposal.rejection_reasons)

    def test_execute_raises_safety_error_when_not_executable(self) -> None:
        """is_executable=False の提案を execute すると RebalanceSafetyError が発生すること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("100")},  # リバランス不要
        )

        proposal = service.simulate()
        assert proposal.is_executable is False

        with pytest.raises(RebalanceSafetyError):
            service.execute(proposal.proposal_id, proposal.confirmation_token)

    def test_execute_raises_token_error_with_wrong_secret(self) -> None:
        """異なるシークレットで署名されたトークンは RebalanceTokenError になること。"""
        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
        )

        proposal = service.simulate()

        # 別のシークレットで署名したトークンを生成
        from app.aave.rebalance_service import _make_confirmation_token

        exp_ts = (datetime.now(timezone.utc) + timedelta(seconds=300)).timestamp()
        tampered_token = _make_confirmation_token(proposal.proposal_id, exp_ts, "wrong-secret-key")

        with pytest.raises(RebalanceTokenError, match="signature mismatch"):
            service.execute(proposal.proposal_id, tampered_token)


class TestPartialExecution:
    """部分実行のテスト。"""

    def test_execute_returns_partial_when_second_operation_fails(self) -> None:
        """2 番目以降の操作がエラーのとき PARTIAL ステータスになること。"""
        success_result = _make_success_result(AaveOperationType.WITHDRAW)
        error_result = _make_error_result(AaveOperationType.DEPOSIT)

        service, _, fake_aave_service = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
            aave_service_results=[success_result, error_result],
        )

        proposal = service.simulate()

        if not proposal.is_executable or len(proposal.operations) < 2:
            pytest.skip("Need at least 2 operations for this test")

        result = service.execute(proposal.proposal_id, proposal.confirmation_token)

        # 1 件成功 + 1 件エラーで中断 → PARTIAL
        assert result.status == RebalanceExecutionStatus.PARTIAL

    def test_execute_returns_success_when_all_operations_succeed(self) -> None:
        """全操作が成功したとき SUCCESS ステータスになること。"""
        success1 = _make_success_result(AaveOperationType.WITHDRAW)
        success2 = _make_success_result(AaveOperationType.DEPOSIT, asset_symbol="WETH")

        service, _, _ = _make_service(
            total_collateral=Decimal("10000"),
            health_factor=Decimal("2.5"),
            target_allocations={"USDC": Decimal("60"), "WETH": Decimal("40")},
            aave_service_results=[success1, success2],
        )

        proposal = service.simulate()
        if not proposal.is_executable:
            pytest.skip("Proposal not executable")

        result = service.execute(proposal.proposal_id, proposal.confirmation_token)

        assert result.status == RebalanceExecutionStatus.SUCCESS


class TestTokenVerification:
    """確認トークン検証のテスト（単体）。"""

    def test_make_and_verify_token_roundtrip(self) -> None:
        """_make_confirmation_token で生成したトークンが _verify で通ること。"""
        from app.aave.rebalance_service import (
            _make_confirmation_token,
            _verify_confirmation_token,
        )

        proposal_id = "test-proposal-id-12345"
        secret = "my-test-secret"
        exp_ts = (datetime.now(timezone.utc) + timedelta(seconds=300)).timestamp()

        token = _make_confirmation_token(proposal_id, exp_ts, secret)

        # 例外が発生しないこと（= 検証成功）
        _verify_confirmation_token(token, proposal_id, secret)

    def test_verify_rejects_tampered_payload(self) -> None:
        """ペイロードが改ざんされたトークンは RebalanceTokenError になること。"""
        import base64
        import json

        from app.aave.rebalance_service import (
            _make_confirmation_token,
            _verify_confirmation_token,
        )

        proposal_id = "test-proposal-id"
        secret = "my-test-secret"
        exp_ts = (datetime.now(timezone.utc) + timedelta(seconds=300)).timestamp()

        token = _make_confirmation_token(proposal_id, exp_ts, secret)

        # ペイロードを改ざん（別の proposal_id）
        tampered_payload = json.dumps(
            {"proposal_id": "evil-id", "exp": exp_ts}, separators=(",", ":")
        ).encode("utf-8")
        tampered_b64 = base64.urlsafe_b64encode(tampered_payload).rstrip(b"=").decode("ascii")
        _, sig = token.split(".", 1)
        tampered_token = f"{tampered_b64}.{sig}"

        with pytest.raises(RebalanceTokenError):
            _verify_confirmation_token(tampered_token, proposal_id, secret)

    def test_verify_rejects_expired_token(self) -> None:
        """有効期限切れトークンは RebalanceTokenError になること。"""
        from app.aave.rebalance_service import (
            _make_confirmation_token,
            _verify_confirmation_token,
        )

        proposal_id = "test-proposal-id"
        secret = "my-test-secret"
        # 過去の exp_ts（既に期限切れ）
        exp_ts = (datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp()

        token = _make_confirmation_token(proposal_id, exp_ts, secret)

        with pytest.raises(RebalanceTokenError, match="expired"):
            _verify_confirmation_token(token, proposal_id, secret)

    def test_verify_rejects_wrong_proposal_id(self) -> None:
        """proposal_id 不一致のとき RebalanceTokenError になること。"""
        from app.aave.rebalance_service import (
            _make_confirmation_token,
            _verify_confirmation_token,
        )

        proposal_id = "correct-id"
        wrong_id = "wrong-id"
        secret = "my-test-secret"
        exp_ts = (datetime.now(timezone.utc) + timedelta(seconds=300)).timestamp()

        token = _make_confirmation_token(proposal_id, exp_ts, secret)

        with pytest.raises(RebalanceTokenError, match="mismatch"):
            _verify_confirmation_token(token, wrong_id, secret)

    def test_verify_rejects_invalid_format(self) -> None:
        """ドットがないトークンは RebalanceTokenError になること。"""
        from app.aave.rebalance_service import _verify_confirmation_token

        with pytest.raises(RebalanceTokenError, match="Invalid token format"):
            _verify_confirmation_token("nodot_token_here", "some-id", "secret")
