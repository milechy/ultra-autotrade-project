# backend/app/aave/rebalance_service.py

"""
Aave ポートフォリオ・リバランスのコアロジック。

責務:
- 現在の配分と目標配分の差分計算
- リバランス提案 (RebalanceProposal) の生成
- 確認トークン (HMAC + base64) の発行・検証
- 提案実行 (execute) と結果記録
- 全操作で Decimal のみ使用 (float 禁止)
- WITHDRAW 操作を DEPOSIT より先に実行する
- いずれかの操作が ERROR → 即座に中断
"""

import base64
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from app.ai.schemas import TradeAction
from app.automation.monitoring_service import MonitoringService

from .client import AaveClient, AaveClientError
from .config import AaveSettings
from .rebalance_config import RebalanceSettings
from .rebalance_schemas import (
    AssetAllocation,
    ProposedOperation,
    RebalanceExecutionStatus,
    RebalanceHistoryEntry,
    RebalanceProposal,
    RebalanceResult,
    RebalanceStatusResponse,
)
from .schemas import (
    AaveOperationMode,
    AaveOperationType,
)
from .state_manager import AaveStateManager

logger = logging.getLogger(__name__)

# 確認トークンのアルゴリズム
_HMAC_ALGORITHM = "sha256"

# ポートフォリオ総資産 0 の場合に除算ゼロを防ぐ最小値
_MIN_TOTAL_USD = Decimal("0.000001")


class RebalanceTokenError(Exception):
    """確認トークンの検証失敗。"""


class RebalanceProposalNotFoundError(Exception):
    """指定された proposal_id が見つからない。"""


class RebalanceSafetyError(Exception):
    """安全制約違反（緊急停止・HF 不足など）。"""


def _make_confirmation_token(
    proposal_id: str,
    exp_timestamp: float,
    secret: str,
) -> str:
    """
    HMAC-SHA256 ベースの確認トークンを生成する。

    フォーマット: base64url(payload_json) + "." + base64url(hmac_signature)

    NOTE: PyJWT を使わず hashlib + hmac + base64 のみを使用する。
    秘密鍵・全トークンをログに出力してはいけない。
    """
    payload = {"proposal_id": proposal_id, "exp": exp_timestamp}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")

    sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        _HMAC_ALGORITHM,
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")

    return f"{payload_b64}.{sig_b64}"


def _verify_confirmation_token(
    token: str,
    expected_proposal_id: str,
    secret: str,
) -> None:
    """
    確認トークンを検証する。

    - HMAC 署名の一致確認（定数時間比較）
    - 有効期限チェック
    - proposal_id の一致確認

    Raises:
        RebalanceTokenError: 検証に失敗した場合。
    """
    parts = token.split(".", 1)
    if len(parts) != 2:
        raise RebalanceTokenError("Invalid token format")

    payload_b64, provided_sig_b64 = parts

    # 期待署名を計算
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        _HMAC_ALGORITHM,
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")

    # 定数時間比較（タイミング攻撃対策）
    if not hmac.compare_digest(provided_sig_b64, expected_sig_b64):
        raise RebalanceTokenError("Token signature mismatch")

    # ペイロードデコード
    # base64 パディングを補正
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64_padded = payload_b64 + "=" * padding
    else:
        payload_b64_padded = payload_b64

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64_padded)
        payload = json.loads(payload_bytes)
    except Exception as exc:
        raise RebalanceTokenError(f"Token payload decode error: {exc}") from exc

    # 有効期限チェック
    exp = payload.get("exp")
    if exp is None:
        raise RebalanceTokenError("Token missing 'exp' field")

    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts > float(exp):
        raise RebalanceTokenError("Token has expired")

    # proposal_id の一致確認
    token_proposal_id = payload.get("proposal_id")
    if token_proposal_id != expected_proposal_id:
        raise RebalanceTokenError(
            f"Token proposal_id mismatch: expected {expected_proposal_id!r}, "
            f"got {token_proposal_id!r}"
        )


class RebalanceService:
    """
    Aave ポートフォリオ・リバランスのコアサービス。

    - simulate() でリバランス提案を生成し、確認トークンを発行する
    - execute() でトークン検証後に実際の操作を実行する
    - 全ての金額計算は Decimal を使用する (float 禁止)
    - WITHDRAW は DEPOSIT より先に実行する
    """

    def __init__(
        self,
        aave_client: AaveClient,
        aave_service: Any,  # AaveService (型循環を避けるため Any)
        rebalance_settings: RebalanceSettings,
        aave_settings: AaveSettings,
        state_manager: AaveStateManager,
        monitoring_service: MonitoringService,
    ) -> None:
        self._client = aave_client
        self._aave_service = aave_service
        self._rb_settings = rebalance_settings
        self._aave_settings = aave_settings
        self._state_manager = state_manager
        self._monitoring = monitoring_service

        self._pending_proposals: dict[str, RebalanceProposal] = {}
        self._history: list[RebalanceHistoryEntry] = []
        self._last_rebalance_at: Optional[datetime] = None

    # ---- 内部ヘルパー --------------------------------------------------

    def _now(self) -> datetime:
        """テストしやすさのために現在時刻取得をメソッド化。"""
        return datetime.now(timezone.utc)

    def _get_wallet_address(self) -> str:
        """ウォレットアドレスを環境変数または設定から取得する。"""
        addr = os.environ.get("AAVE_WALLET_ADDRESS", "")
        if not addr:
            # AaveSettings に wallet_address 相当のフィールドがある場合のフォールバック
            addr = getattr(self._aave_settings, "wallet_address", "") or ""
        return addr

    def _cooldown_remaining_seconds(self, now: datetime) -> int:
        """クールダウン残り秒数を返す。0 の場合は即時実行可能。"""
        if self._last_rebalance_at is None:
            return 0

        last = self._last_rebalance_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)

        elapsed = (now - last).total_seconds()
        remaining = self._rb_settings.cooldown_seconds - elapsed
        return max(0, int(remaining))

    def _calculate_allocations(
        self,
        balances: dict[str, Decimal],
        total_usd: Decimal,
    ) -> list[AssetAllocation]:
        """
        現在残高から AssetAllocation リストを計算する。

        target_allocations にないアセットの target_pct は 0 として扱う。
        """
        all_symbols = set(balances.keys()) | set(self._rb_settings.target_allocations.keys())
        result: list[AssetAllocation] = []

        for symbol in sorted(all_symbols):
            current_usd = balances.get(symbol, Decimal("0"))
            if total_usd <= _MIN_TOTAL_USD:
                current_pct = Decimal("0")
            else:
                current_pct = (current_usd / total_usd * Decimal("100")).quantize(Decimal("0.01"))

            target_pct = self._rb_settings.target_allocations.get(symbol, Decimal("0"))
            deviation_pct = (current_pct - target_pct).quantize(Decimal("0.01"))

            result.append(
                AssetAllocation(
                    asset_symbol=symbol,
                    current_amount_usd=current_usd,
                    current_pct=current_pct,
                    target_pct=target_pct,
                    deviation_pct=deviation_pct,
                )
            )

        return result

    def _needs_rebalance(self, allocations: list[AssetAllocation]) -> bool:
        """いずれかの資産が deviation_threshold_pct を超えているか判定する。"""
        threshold = self._rb_settings.deviation_threshold_pct
        return any(abs(a.deviation_pct) > threshold for a in allocations)

    def _calculate_operations(
        self,
        allocations: list[AssetAllocation],
        total_usd: Decimal,
    ) -> list[ProposedOperation]:
        """
        配分乖離から操作リストを計算する。

        - 乖離が threshold 以下のアセットはスキップ
        - deviation > 0 (過剰) → WITHDRAW
        - deviation < 0 (不足) → DEPOSIT
        - 1 回の操作量は total_usd の max_rebalance_pct 以下に制限する
        """
        ops: list[ProposedOperation] = []
        threshold = self._rb_settings.deviation_threshold_pct
        max_pct = self._rb_settings.max_rebalance_pct
        max_op_usd = total_usd * max_pct / Decimal("100")

        for alloc in allocations:
            dev = alloc.deviation_pct
            if abs(dev) <= threshold:
                continue

            # 操作金額 = 乖離率 × 総資産
            raw_amount = abs(dev) / Decimal("100") * total_usd
            amount = min(raw_amount, max_op_usd)
            amount = amount.quantize(Decimal("0.01"))

            if amount <= Decimal("0"):
                continue

            if dev > 0:
                ops.append(
                    ProposedOperation(
                        asset_symbol=alloc.asset_symbol,
                        operation=AaveOperationType.WITHDRAW,
                        amount_usd=amount,
                        reason=(
                            f"{alloc.asset_symbol} is over-allocated by "
                            f"{dev}% (target={alloc.target_pct}%, "
                            f"current={alloc.current_pct}%)"
                        ),
                    )
                )
            else:
                ops.append(
                    ProposedOperation(
                        asset_symbol=alloc.asset_symbol,
                        operation=AaveOperationType.DEPOSIT,
                        amount_usd=amount,
                        reason=(
                            f"{alloc.asset_symbol} is under-allocated by "
                            f"{abs(dev)}% (target={alloc.target_pct}%, "
                            f"current={alloc.current_pct}%)"
                        ),
                    )
                )

        # WITHDRAW を先、DEPOSIT を後に並び替える
        withdrawals = [op for op in ops if op.operation == AaveOperationType.WITHDRAW]
        deposits = [op for op in ops if op.operation == AaveOperationType.DEPOSIT]
        return withdrawals + deposits

    def _check_safety_constraints(
        self,
        operations: list[ProposedOperation],
        total_usd: Decimal,
        health_factor: Decimal,
        now: datetime,
    ) -> list[str]:
        """
        安全制約を全て確認し、拒否理由のリストを返す。

        返値が空リストの場合 = 全ての制約をクリア。
        """
        reasons: list[str] = []

        # state.json の鮮度チェック
        if self._state_manager.is_stale():
            reasons.append("state.json is stale; cannot execute rebalance")
            return reasons  # stale なら他チェックも意味なし

        state = self._state_manager.read_state()

        # emergency_stop
        if state.emergency_stop:
            reasons.append("emergency_stop is True; all Aave operations are blocked")

        # circuit_closed
        if not state.circuit_closed:
            reasons.append("circuit_closed is False; all Aave operations are blocked")

        # モード
        if state.mode == AaveOperationMode.HARD_STOP:
            reasons.append(f"Mode={state.mode.value}; all operations are blocked")
        elif state.mode == AaveOperationMode.SAFE_MODE:
            has_deposit = any(op.operation == AaveOperationType.DEPOSIT for op in operations)
            if has_deposit:
                reasons.append(f"Mode={state.mode.value}; DEPOSIT operations are blocked")

        # MonitoringService の緊急停止
        if not self._monitoring.is_trading_allowed():
            reasons.append("Trading is paused by MonitoringService emergency stop")

        # クールダウン
        cooldown_remaining = self._cooldown_remaining_seconds(now)
        if cooldown_remaining > 0:
            reasons.append(
                f"Cooldown active: {cooldown_remaining}s remaining "
                f"(cooldown={self._rb_settings.cooldown_seconds}s)"
            )

        # ヘルスファクター（提案時点）
        if (
            health_factor != Decimal("inf")
            and health_factor < self._rb_settings.min_health_factor_post
        ):
            reasons.append(
                f"Current health factor {health_factor} is below minimum "
                f"{self._rb_settings.min_health_factor_post}"
            )

        # 単一取引上限 10%
        if total_usd > _MIN_TOTAL_USD:
            max_single_usd = total_usd * Decimal("10") / Decimal("100")
            for op in operations:
                if op.amount_usd > max_single_usd:
                    reasons.append(
                        f"Operation {op.asset_symbol} {op.operation.value} "
                        f"amount {op.amount_usd} USD exceeds 10% of total assets "
                        f"({max_single_usd} USD)"
                    )

        return reasons

    # ---- 公開メソッド --------------------------------------------------

    def get_current_status(self) -> RebalanceStatusResponse:
        """
        現在のポートフォリオ状態を取得して RebalanceStatusResponse を返す。

        1. クライアントからアカウントデータを取得
        2. 現在の配分割合を計算
        3. 目標配分との乖離を計算
        4. リバランスの要否を判定
        5. クールダウン残り時間を計算
        """
        wallet = self._get_wallet_address()
        now = self._now()

        try:
            account_data = self._client.get_account_data(wallet)
            total_usd = account_data.total_collateral_usd
            health_factor = account_data.health_factor
        except AaveClientError as exc:
            logger.error("Failed to fetch account data for status: %s", exc)
            total_usd = Decimal("0")
            health_factor = Decimal("0")

        # ダミー: 現在は collateral 全体を default_asset_symbol として扱う
        # 実際の資産別残高取得は将来の拡張で対応
        default_symbol = self._aave_settings.default_asset_symbol
        balances: dict[str, Decimal] = {default_symbol: total_usd}

        current_allocations = self._calculate_allocations(balances, total_usd)

        # target_allocations に存在する全アセットの目標配分リスト（表示用）
        target_allocations = self._calculate_allocations(
            {sym: Decimal("0") for sym in self._rb_settings.target_allocations},
            Decimal("0"),
        )

        needs_rebalance = self._needs_rebalance(current_allocations)
        cooldown_remaining = self._cooldown_remaining_seconds(now)

        return RebalanceStatusResponse(
            current_allocations=current_allocations,
            target_allocations=target_allocations,
            health_factor=health_factor,
            total_value_usd=total_usd,
            deviation_threshold_pct=self._rb_settings.deviation_threshold_pct,
            needs_rebalance=needs_rebalance,
            last_rebalance_at=self._last_rebalance_at,
            cooldown_remaining_seconds=cooldown_remaining,
        )

    def simulate(self) -> RebalanceProposal:
        """
        リバランス提案を生成する。

        1. 現在の配分状態を取得
        2. リバランス不要の場合 → 非実行可能な提案を返す
        3. 操作リストを計算（WITHDRAW → DEPOSIT の順）
        4. 安全制約チェック
        5. UUID proposal_id と HMAC 確認トークンを生成
        6. _pending_proposals に保存して返す
        """
        wallet = self._get_wallet_address()
        now = self._now()

        try:
            account_data = self._client.get_account_data(wallet)
            total_usd = account_data.total_collateral_usd
            health_factor = account_data.health_factor
        except AaveClientError as exc:
            logger.error("Failed to fetch account data for simulate: %s", exc)
            total_usd = Decimal("0")
            health_factor = Decimal("0")

        default_symbol = self._aave_settings.default_asset_symbol
        balances: dict[str, Decimal] = {default_symbol: total_usd}
        current_allocations = self._calculate_allocations(balances, total_usd)

        proposal_id = str(uuid.uuid4())
        created_at = now

        # リバランス不要の場合
        if not self._needs_rebalance(current_allocations):
            logger.info(
                "simulate: no rebalance needed (all allocations within threshold=%s%%)",
                self._rb_settings.deviation_threshold_pct,
            )
            # 実行不可な提案を返す（トークンは発行するが is_executable=False）
            exp_ts = (
                now + timedelta(seconds=self._rb_settings.confirmation_token_ttl_seconds)
            ).timestamp()
            token = _make_confirmation_token(
                proposal_id, exp_ts, self._rb_settings.confirmation_token_secret
            )

            proposal = RebalanceProposal(
                proposal_id=proposal_id,
                created_at=created_at,
                health_factor_before=health_factor,
                total_value_usd=total_usd,
                allocations=current_allocations,
                operations=[],
                estimated_health_factor_after=health_factor,
                max_single_trade_pct=self._rb_settings.max_rebalance_pct,
                confirmation_token=token,
                is_executable=False,
                rejection_reasons=["No rebalance needed: all allocations are within threshold"],
            )
            self._pending_proposals[proposal_id] = proposal
            return proposal

        # 操作リスト計算
        operations = self._calculate_operations(current_allocations, total_usd)
        logger.info(
            "simulate: calculated %d operations for rebalance",
            len(operations),
        )

        # 安全制約チェック
        rejection_reasons = self._check_safety_constraints(
            operations, total_usd, health_factor, now
        )

        # HF 事後推定: WITHDRAW 操作がある場合は担保減少を考慮した推定HFを計算
        withdraw_ops = [op for op in operations if op.operation == AaveOperationType.WITHDRAW]
        estimated_hf_after: Optional[Decimal]
        if withdraw_ops and health_factor != Decimal("inf") and total_usd > _MIN_TOTAL_USD:
            total_withdraw_usd = sum(op.amount_usd for op in withdraw_ops)
            new_collateral_ratio = (total_usd - total_withdraw_usd) / total_usd
            if new_collateral_ratio > Decimal("0"):
                estimated_hf_after = (health_factor * new_collateral_ratio).quantize(
                    Decimal("0.0001")
                )
            else:
                estimated_hf_after = Decimal("0")
            if estimated_hf_after < self._rb_settings.min_health_factor_post:
                rejection_reasons.append(
                    f"Estimated health factor after withdraw ({estimated_hf_after}) "
                    f"is below minimum ({self._rb_settings.min_health_factor_post})"
                )
        elif health_factor != Decimal("inf"):
            estimated_hf_after = health_factor
        else:
            estimated_hf_after = None

        is_executable = len(rejection_reasons) == 0

        if not is_executable:
            logger.warning(
                "simulate: proposal is NOT executable. reasons=%s",
                rejection_reasons,
            )
        else:
            logger.info("simulate: proposal passed all safety checks, is_executable=True")

        # 確認トークン生成
        exp_ts = (
            now + timedelta(seconds=self._rb_settings.confirmation_token_ttl_seconds)
        ).timestamp()
        token = _make_confirmation_token(
            proposal_id, exp_ts, self._rb_settings.confirmation_token_secret
        )
        # トークン全体はログに出さない
        logger.info(
            "simulate: confirmation token generated for proposal_id=%s (exp=%s)",
            proposal_id,
            exp_ts,
        )

        proposal = RebalanceProposal(
            proposal_id=proposal_id,
            created_at=created_at,
            health_factor_before=health_factor,
            total_value_usd=total_usd,
            allocations=current_allocations,
            operations=operations,
            estimated_health_factor_after=estimated_hf_after,
            max_single_trade_pct=self._rb_settings.max_rebalance_pct,
            confirmation_token=token,
            is_executable=is_executable,
            rejection_reasons=rejection_reasons,
        )
        self._pending_proposals[proposal_id] = proposal
        return proposal

    def execute(self, proposal_id: str, confirmation_token: str) -> RebalanceResult:
        """
        リバランス提案を実行する。

        1. confirmation_token を検証（HMAC + 有効期限）
        2. _pending_proposals から提案を取得
        3. 全安全制約を再チェック
        4. WITHDRAW → DEPOSIT の順で操作を実行
        5. ERROR が発生した場合は即座に中断
        6. 実行結果を _history に記録
        7. _last_rebalance_at を更新
        8. _pending_proposals から削除

        Returns:
            RebalanceResult: 実行結果
        """
        now = self._now()

        # 1. トークン検証
        try:
            _verify_confirmation_token(
                confirmation_token,
                proposal_id,
                self._rb_settings.confirmation_token_secret,
            )
        except RebalanceTokenError as exc:
            logger.warning(
                "execute: token verification failed for proposal_id=%s: %s", proposal_id, exc
            )
            raise

        # 2. 提案取得
        proposal = self._pending_proposals.get(proposal_id)
        if proposal is None:
            logger.warning("execute: proposal not found: proposal_id=%s", proposal_id)
            raise RebalanceProposalNotFoundError(f"Proposal not found: {proposal_id}")

        if not proposal.is_executable:
            logger.warning(
                "execute: proposal is not executable: proposal_id=%s, reasons=%s",
                proposal_id,
                proposal.rejection_reasons,
            )
            raise RebalanceSafetyError(f"Proposal is not executable: {proposal.rejection_reasons}")

        # 3. 安全制約の再チェック（時間経過による状態変化を考慮）
        wallet = self._get_wallet_address()
        try:
            account_data = self._client.get_account_data(wallet)
            current_hf = account_data.health_factor
            total_usd = account_data.total_collateral_usd
        except AaveClientError as exc:
            logger.error("execute: failed to fetch account data before execution: %s", exc)
            current_hf = Decimal("0")
            total_usd = proposal.total_value_usd

        re_check_reasons = self._check_safety_constraints(
            list(proposal.operations), total_usd, current_hf, now
        )
        if re_check_reasons:
            logger.warning(
                "execute: safety re-check failed for proposal_id=%s: %s",
                proposal_id,
                re_check_reasons,
            )
            raise RebalanceSafetyError(f"Safety constraints failed on re-check: {re_check_reasons}")

        health_factor_before = current_hf

        # 4. 操作を順次実行（WITHDRAW → DEPOSIT は simulate 時に保証済み）
        from app.aave.schemas import AaveOperationResult, AaveOperationStatus, AaveOperationType

        executed_results: list[AaveOperationResult] = []
        aborted = False

        for op in proposal.operations:
            if op.operation == AaveOperationType.NOOP:
                continue

            # TradeAction へのマッピング
            if op.operation == AaveOperationType.WITHDRAW:
                action = TradeAction.SELL
            elif op.operation == AaveOperationType.DEPOSIT:
                action = TradeAction.BUY
            else:
                logger.warning(
                    "execute: unexpected operation type %s; skipping",
                    op.operation,
                )
                continue

            logger.info(
                "execute: dispatching %s %s %s USD (proposal_id=%s)",
                op.operation.value,
                op.asset_symbol,
                op.amount_usd,
                proposal_id,
            )

            dry_run = self._rb_settings.shadow_mode
            result = self._aave_service.execute_rebalance(
                action=action,
                amount=op.amount_usd,
                asset_symbol=op.asset_symbol,
                dry_run=dry_run,
            )
            executed_results.append(result)

            if result.status == AaveOperationStatus.ERROR:
                logger.error(
                    "execute: operation %s %s returned ERROR; aborting remaining operations. "
                    "message=%s",
                    op.operation.value,
                    op.asset_symbol,
                    result.message,
                )
                aborted = True
                break

        # 5. 実行後の HF 取得
        health_factor_after: Optional[Decimal] = None
        try:
            post_account = self._client.get_account_data(wallet)
            health_factor_after = post_account.health_factor
        except AaveClientError as exc:
            logger.error("execute: failed to fetch health factor after execution: %s", exc)

        # 6. 最終ステータス判定
        if aborted:
            if len(executed_results) > 1:
                final_status = RebalanceExecutionStatus.PARTIAL
            else:
                final_status = RebalanceExecutionStatus.FAILED
        elif not executed_results:
            final_status = RebalanceExecutionStatus.ABORTED
        else:
            all_success = all(r.status == AaveOperationStatus.SUCCESS for r in executed_results)
            final_status = (
                RebalanceExecutionStatus.SUCCESS
                if all_success
                else RebalanceExecutionStatus.PARTIAL
            )

        executed_at = self._now()

        result_obj = RebalanceResult(
            proposal_id=proposal_id,
            executed_at=executed_at,
            operations=executed_results,
            health_factor_before=health_factor_before,
            health_factor_after=health_factor_after,
            status=final_status,
            message=(
                f"Rebalance {final_status.value}: "
                f"{len(executed_results)} operation(s) executed"
                + (" (aborted on error)" if aborted else "")
            ),
        )

        # 7. 履歴に記録
        history_entry = RebalanceHistoryEntry(
            proposal_id=proposal_id,
            created_at=proposal.created_at,
            executed_at=executed_at,
            status=final_status,
            total_value_usd=proposal.total_value_usd,
            operations_count=len(executed_results),
            health_factor_before=health_factor_before,
            health_factor_after=health_factor_after,
        )
        self._history.append(history_entry)
        logger.info(
            "execute: recorded history entry for proposal_id=%s, status=%s",
            proposal_id,
            final_status.value,
        )

        # 8. _last_rebalance_at 更新
        if final_status in (RebalanceExecutionStatus.SUCCESS, RebalanceExecutionStatus.PARTIAL):
            self._last_rebalance_at = executed_at
            logger.info(
                "execute: updated _last_rebalance_at to %s",
                executed_at.isoformat(),
            )

        # 9. pending から削除
        self._pending_proposals.pop(proposal_id, None)

        return result_obj

    def get_history(self, limit: int = 20) -> list[RebalanceHistoryEntry]:
        """リバランス履歴を新しい順に最大 limit 件返す。"""
        return self._history[-limit:]
