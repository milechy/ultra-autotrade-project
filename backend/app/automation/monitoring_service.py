# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/monitoring_service.py

"""
監視・アラート・緊急停止ロジック本体。

docs/08_automation_rules.md / 13_security_design.md / 15_rollback_procedures.md の
以下のルールをコード化することを主目的とする。

- 死活監視（応答時間）
- 過剰取引監視
- 緊急停止条件（ヘルスファクター・価格変動・エラー率）

このモジュールは **外部サービスへの通知は行わない**。
あくまで「状態管理」と「判定」を担い、通知やレポート生成は別モジュールから
AutomationStatus / MonitoringEvent / AutomationReportSummary を参照して行う前提。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Deque, Dict, List, Optional, Tuple

from app.notifications.schemas import NotificationChannel, NotificationMessage, NotificationSeverity
from app.notifications.service import CompositeNotificationService

from .schemas import (
    AlertLevel,
    AutomationStatus,
    ComponentType,
    DashboardSnapshot,
    HealthFactorStatus,
    LatencyRecord,
    MetricAggregate,
    MetricPoint,
    MonitoringEvent,
    TradeActivityRecord,
)

logger = logging.getLogger(__name__)

_HEALTH_FACTOR_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class MonitoringService:
    """
    Phase5 の監視・緊急停止ロジックの集約ポイント。

    - record_* 系メソッドでメトリクスを登録
    - しきい値を超えた場合は MonitoringEvent を発行
    - is_trading_allowed / get_status で現在の状態を参照
    """

    def __init__(
        self,
        *,
        latency_warning_threshold_s: float = 10.0,
        latency_alert_threshold_s: float = 30.0,
        healthfactor_warning_threshold: Decimal = Decimal("1.8"),
        healthfactor_emergency_threshold: Decimal = Decimal("1.6"),
        price_change_alert_threshold_pct: float = 20.0,
        max_events: int = 1000,
        max_latency_records: int = 1000,
        max_trade_records: int = 1000,
        max_healthfactor_records: int = 1000,
        enable_state_sync: bool = True,
        notification_service: Optional[CompositeNotificationService] = None,
        error_rate_window_size: int = 100,
        ai_error_rate_threshold: float = 0.20,
    ) -> None:
        # 閾値
        self._latency_warning_threshold_s = float(latency_warning_threshold_s)
        self._latency_alert_threshold_s = float(latency_alert_threshold_s)
        self._hf_warning_threshold = Decimal(healthfactor_warning_threshold)
        self._hf_emergency_threshold = Decimal(healthfactor_emergency_threshold)
        self._price_change_alert_threshold_pct = float(price_change_alert_threshold_pct)

        # state.json 同期設定
        self._enable_state_sync = enable_state_sync
        self._notification_service = notification_service

        # エラー率監視設定
        self._error_rate_window_size = error_rate_window_size
        self._ai_error_rate_threshold = ai_error_rate_threshold
        self._error_timestamps: Dict[str, Deque[datetime]] = {}

        # 状態
        self._events: Deque[MonitoringEvent] = deque(maxlen=max_events)
        self._latencies: Deque[LatencyRecord] = deque(maxlen=max_latency_records)
        self._trades: Deque[TradeActivityRecord] = deque(maxlen=max_trade_records)
        # ヘルスファクターの履歴（レポート集計用）
        self._health_factors: Deque[Tuple[datetime, Optional[Decimal]]] = deque(
            maxlen=max_healthfactor_records
        )

        self._trading_paused: bool = False
        self._emergency_reason: Optional[str] = None
        self._last_health_factor: Optional[Decimal] = None
        self._last_price_change_24h: Optional[float] = None
        self._last_event_level: AlertLevel = AlertLevel.INFO

        # 起動時に state.json から緊急停止状態を復元（OR 条件維持）
        if enable_state_sync:
            self._restore_state_from_file()

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------
    def _now(self, at: Optional[datetime]) -> datetime:
        if at is not None:
            # タイムゾーン未設定の場合も UTC に寄せる
            if at.tzinfo is None:
                return at.replace(tzinfo=timezone.utc)
            return at
        return datetime.now(timezone.utc)

    def _normalize_bound(self, ts: Optional[datetime], default: datetime) -> datetime:
        """
        範囲指定用の境界時刻を正規化する。

        - None の場合は default を使用
        - tzinfo がない場合は UTC とみなす
        """
        if ts is None:
            return default
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts

    def _append_event(self, event: MonitoringEvent) -> MonitoringEvent:
        self._events.append(event)
        # より強いレベルが来たら上書き
        level_order = {
            AlertLevel.INFO: 0,
            AlertLevel.WARNING: 1,
            AlertLevel.ALERT: 2,
            AlertLevel.CRITICAL: 3,
            AlertLevel.EMERGENCY: 4,
        }
        if level_order[event.level] >= level_order[self._last_event_level]:
            self._last_event_level = event.level
        return event

    def _restore_state_from_file(self) -> None:
        """起動時に state.json から緊急停止状態を復元する。"""
        try:
            from app.aave.state_manager import StateFileNotFoundError, read_system_state
            try:
                current = read_system_state()
                if current.emergency_stop:
                    self._trading_paused = True
                    reason = getattr(current, "reason", None)
                    self._emergency_reason = reason or "Restored from state.json on startup"
                    logger.info(
                        "Restored emergency_stop=True from state.json (reason=%s)",
                        self._emergency_reason,
                    )
            except StateFileNotFoundError:
                pass  # 初回起動時は state.json なし
        except Exception as exc:
            logger.warning("Failed to restore emergency state from file: %s", exc)

    def _sync_state_file(
        self,
        health_factor: Optional[Decimal],
        hf_triggered_emergency: bool,
        reason: Optional[str],
        now: datetime,
    ) -> None:
        """
        state.json にシステム状態を同期する。

        - HF >= 1.8: NORMAL
        - 1.6 <= HF < 1.8: SAFE_MODE
        - HF < 1.6: HARD_STOP

        書き込み失敗時はログ出力のみ（サービス継続）。
        circuit_closed と既存の emergency_stop=True は維持（OR 条件）。
        """
        if not self._enable_state_sync:
            return

        try:
            from app.aave.config import get_aave_settings
            from app.aave.schemas import AaveOperationMode, AaveSystemState
            from app.aave.state_manager import (
                StateFileNotFoundError,
                StateFileParseError,
                get_default_state,
                get_safe_default_state,
                read_system_state,
                write_system_state,
            )

            settings = get_aave_settings()

            # 現在の state を読み込み（circuit_closed, emergency_stop を維持するため）
            try:
                current = read_system_state()
            except StateFileNotFoundError:
                # 初回起動時はデフォルト値を使用
                current = get_default_state()
            except StateFileParseError:
                # パースエラー時は安全側デフォルトを使用（オペレーター設定を保護）
                logger.warning(
                    "State file parse error, using SAFE default for sync "
                    "(emergency_stop=True, circuit_closed=False)"
                )
                current = get_safe_default_state()

            # モード判定
            if health_factor is None:
                mode = AaveOperationMode.NORMAL
            elif health_factor < self._hf_emergency_threshold:
                mode = AaveOperationMode.HARD_STOP
            elif health_factor < self._hf_warning_threshold:
                mode = AaveOperationMode.SAFE_MODE
            else:
                mode = AaveOperationMode.NORMAL

            # emergency_stop は OR 条件で更新
            # - 既存の emergency_stop=True は維持（オペレーター設定を尊重）
            # - HF < 1.6 で新たに True にする
            # - False に戻すのは clear_emergency_stop() 呼び出し時のみ
            existing_emergency = current.emergency_stop
            final_emergency_stop = existing_emergency or hf_triggered_emergency

            # reason も既存を維持（新しい理由がある場合のみ更新）
            final_reason = reason if reason else current.reason

            new_state = AaveSystemState(
                emergency_stop=final_emergency_stop,
                mode=mode,
                health_factor=health_factor,
                last_update=now,
                reason=final_reason,
                circuit_closed=current.circuit_closed,  # 既存値を維持
                stale_threshold_seconds=settings.state_stale_threshold_seconds,
            )

            write_system_state(new_state)
            logger.debug(
                "Synced state file: mode=%s, emergency_stop=%s, hf=%s",
                mode.value,
                final_emergency_stop,
                health_factor,
            )

        except Exception as exc:
            logger.warning("Failed to sync state file: %s", exc)

    def _notify(
        self,
        severity: NotificationSeverity,
        title: str,
        body: str,
    ) -> None:
        """通知を送信する。未設定時や失敗時はスキップ（fail-safe）。"""
        if self._notification_service is None:
            return
        try:
            message = NotificationMessage(
                channel=NotificationChannel.SLACK,
                severity=severity,
                title=title,
                body=body,
            )
            self._notification_service.send(message)
        except Exception as exc:
            logger.warning("Failed to send notification: %s", exc)

    # ------------------------------------------------------------------
    # 公開 API: メトリクス登録
    # ------------------------------------------------------------------
    def record_latency(
        self,
        component: ComponentType,
        duration: timedelta | float,
        *,
        at: Optional[datetime] = None,
    ) -> Optional[MonitoringEvent]:
        """
        応答時間を記録し、しきい値を超えていればイベントを発行する。

        docs/08_automation_rules.md:
        - 応答時間 > 10秒 → 警告
        - 応答時間 > 30秒 → アラート
        """
        now = self._now(at)
        seconds = (
            float(duration.total_seconds()) if isinstance(duration, timedelta) else float(duration)
        )
        millis = int(seconds * 1000)

        record = LatencyRecord(
            component=component,
            timestamp=now,
            duration_ms=millis,
        )
        self._latencies.append(record)

        if seconds > self._latency_alert_threshold_s:
            event = MonitoringEvent(
                timestamp=now,
                component=component,
                level=AlertLevel.ALERT,
                code="LATENCY_ALERT",
                message=f"Latency {seconds:.1f}s exceeds alert threshold.",
            )
            # メトリクス情報を添付
            event.metric = MetricPoint(
                metric_id=f"latency_{component.name.lower()}_s",
                value=Decimal(str(seconds)),
                unit="s",
                labels={"component": component.name},
                recorded_at=now,
            )
            return self._append_event(event)

        if seconds > self._latency_warning_threshold_s:
            event = MonitoringEvent(
                timestamp=now,
                component=component,
                level=AlertLevel.WARNING,
                code="LATENCY_WARNING",
                message=f"Latency {seconds:.1f}s exceeds warning threshold.",
            )
            # メトリクス情報を添付
            event.metric = MetricPoint(
                metric_id=f"latency_{component.name.lower()}_s",
                value=Decimal(str(seconds)),
                unit="s",
                labels={"component": component.name},
                recorded_at=now,
            )
            return self._append_event(event)

        return None

    def record_trade(
        self,
        component: ComponentType,
        action: str,
        *,
        at: Optional[datetime] = None,
    ) -> None:
        """
        過剰取引監視用にトレード（またはシグナル）を記録する。

        Phase5 のこのタイミングでは「カウントの記録」のみに留め、
        実際の過剰取引アラート判定は将来拡張とする。
        （既存の OctoBot レート制限・Aave クールダウンが一次防波堤）
        """
        now = self._now(at)
        record = TradeActivityRecord(
            component=component,
            action=str(action),
            timestamp=now,
        )
        self._trades.append(record)

    def record_health_factor(
        self,
        value: Optional[Decimal],
        *,
        at: Optional[datetime] = None,
    ) -> HealthFactorStatus:
        """
        ヘルスファクターを記録し、警告・緊急停止判定を行う。

        docs/08_automation_rules.md / 15_rollback_procedures.md:
        - ヘルスファクター < 1.8 → 警告（SAFE_MODE）
        - ヘルスファクター < 1.6 → 緊急停止（HARD_STOP）

        state.json への同期も行う（enable_state_sync=True の場合）。
        """
        now = self._now(at)
        self._last_health_factor = value
        self._health_factors.append((now, value))

        if value is None:
            # HF=None は「借入なし（ポジションなし）」を意味する
            # state.json は更新する（last_update を最新に保つため）
            self._sync_state_file(
                health_factor=None,
                hf_triggered_emergency=False,
                reason=None,
                now=now,
            )
            return HealthFactorStatus(
                current=None,
                level=AlertLevel.INFO,
                is_emergency=False,
            )

        level: AlertLevel = AlertLevel.INFO
        is_emergency = False
        reason: Optional[str] = None

        if value < self._hf_emergency_threshold:
            level = AlertLevel.EMERGENCY
            is_emergency = True
            self._trading_paused = True
            reason = (
                f"health factor {value} below emergency threshold {self._hf_emergency_threshold}"
            )
            if self._emergency_reason is None:
                self._emergency_reason = reason
            event = MonitoringEvent(
                timestamp=now,
                component=ComponentType.AAVE,
                level=level,
                code="HF_BELOW_EMERGENCY",
                message=reason,
            )
            event.metric = MetricPoint(
                metric_id="aave_health_factor_current",
                value=value,
                unit="ratio",
                labels={"component": "AAVE"},
                recorded_at=now,
            )
            self._append_event(event)

        elif value < self._hf_warning_threshold:
            level = AlertLevel.WARNING
            reason = f"health factor {value} below warning threshold {self._hf_warning_threshold}"
            event = MonitoringEvent(
                timestamp=now,
                component=ComponentType.AAVE,
                level=level,
                code="HF_BELOW_WARNING",
                message=reason,
            )
            event.metric = MetricPoint(
                metric_id="aave_health_factor_current",
                value=value,
                unit="ratio",
                labels={"component": "AAVE"},
                recorded_at=now,
            )
            self._append_event(event)

        # state.json への同期
        self._sync_state_file(
            health_factor=value,
            hf_triggered_emergency=is_emergency,
            reason=reason,
            now=now,
        )

        return HealthFactorStatus(
            current=value,
            level=level,
            is_emergency=is_emergency,
        )

    def record_price_change_24h(
        self,
        percent_change: float,
        *,
        at: Optional[datetime] = None,
    ) -> Optional[MonitoringEvent]:
        """
        24時間の価格変動率を記録し、アラート判定を行う。

        docs/08_automation_rules.md:
        - 資産変動 > 20%/日 → アラート
        """
        now = self._now(at)
        self._last_price_change_24h = float(percent_change)

        if abs(percent_change) > self._price_change_alert_threshold_pct:
            event = MonitoringEvent(
                timestamp=now,
                component=ComponentType.SYSTEM,
                level=AlertLevel.ALERT,
                code="PRICE_CHANGE_ALERT",
                message=(
                    f"24h price change {percent_change:.1f}% exceeds "
                    f"alert threshold {self._price_change_alert_threshold_pct:.1f}%."
                ),
            )
            event.metric = MetricPoint(
                metric_id="portfolio_value_change_1d_pct",
                value=Decimal(str(percent_change)),
                unit="percent",
                labels={"window": "24h"},
                recorded_at=now,
            )
            return self._append_event(event)

        return None

    def record_error(
        self,
        component: ComponentType,
        *,
        at: Optional[datetime] = None,
    ) -> Optional[MonitoringEvent]:
        """
        コンポーネントのAPIエラーを記録し、エラー率が閾値を超えた場合にアラートを発行する。

        docs/08_automation_rules.md:
        - AI API エラー率 > 20% → アラート（取引停止）

        Args:
            component: エラーが発生したコンポーネント
            at: 記録時刻（None の場合は現在時刻）

        Returns:
            エラー率が閾値を超えた場合は MonitoringEvent、それ以外は None
        """
        now = self._now(at)
        key = component.value
        if key not in self._error_timestamps:
            self._error_timestamps[key] = deque(maxlen=self._error_rate_window_size)
        self._error_timestamps[key].append(now)

        total = len(self._error_timestamps[key])
        if total == 0:
            return None

        error_rate = total / self._error_rate_window_size
        if error_rate > self._ai_error_rate_threshold:
            event = MonitoringEvent(
                timestamp=now,
                component=component,
                level=AlertLevel.ALERT,
                code="ERROR_RATE_HIGH",
                message=(
                    f"Error rate {error_rate:.1%} for {component.value} "
                    f"exceeds threshold {self._ai_error_rate_threshold:.1%}."
                ),
            )
            event.metric = MetricPoint(
                metric_id=f"error_rate_{component.name.lower()}",
                value=Decimal(str(round(error_rate, 4))),
                unit="ratio",
                labels={"component": component.name},
                recorded_at=now,
            )
            return self._append_event(event)

        return None

    # ------------------------------------------------------------------
    # 公開 API: 状態参照・緊急停止制御
    # ------------------------------------------------------------------
    def is_trading_allowed(self) -> bool:
        """
        現在トレードを許可してよいかを返す。

        - 緊急停止フラグが立っている場合は False
        """
        return not self._trading_paused

    def activate_emergency_stop(
        self,
        *,
        reason: str,
        component: ComponentType = ComponentType.SYSTEM,
        at: Optional[datetime] = None,
    ) -> MonitoringEvent:
        """
        手動／その他条件で緊急停止を有効化する。

        Aave 側の「ポジションを増やさない」ロジックと組み合わせて、
        資金を守る最後の防波堤として機能する。
        """
        now = self._now(at)
        self._trading_paused = True
        self._emergency_reason = reason

        event = MonitoringEvent(
            timestamp=now,
            component=component,
            level=AlertLevel.EMERGENCY,
            code="EMERGENCY_STOP",
            message=reason,
        )

        # state.json に永続化（再起動後も緊急停止状態を維持するため）
        self._sync_state_file(
            health_factor=self._last_health_factor,
            hf_triggered_emergency=True,
            reason=reason,
            now=now,
        )

        # Slack通知
        hf_info = ""
        if self._last_health_factor is not None:
            hf_info = f"\nHealth Factor: {self._last_health_factor}"
        self._notify(
            NotificationSeverity.EMERGENCY,
            "🚨 緊急停止が発動されました",
            f"{reason}{hf_info}",
        )

        return self._append_event(event)

    def clear_emergency_stop(self) -> None:
        """
        緊急停止状態を解除する。

        自動解除は危険なので、基本的には運用者が明示的に呼び出す想定。
        state.json も同期して emergency_stop=False にする。
        """
        self._trading_paused = False
        self._emergency_reason = None

        # Slack通知
        self._notify(
            NotificationSeverity.INFO,
            "✅ 緊急停止が解除されました",
            "緊急停止状態が手動で解除されました。取引を再開します。",
        )

        # state.json も同期
        if self._enable_state_sync:
            try:
                from app.aave.schemas import AaveOperationMode, AaveSystemState
                from app.aave.state_manager import (
                    StateFileNotFoundError,
                    StateFileParseError,
                    get_default_state,
                    get_safe_default_state,
                    read_system_state,
                    write_system_state,
                )

                try:
                    current = read_system_state()
                except StateFileNotFoundError:
                    # 初回起動時はデフォルト値を使用
                    current = get_default_state()
                except StateFileParseError:
                    # パースエラー時は安全側デフォルトを使用
                    # ただし clear_emergency_stop() が呼ばれているので
                    # emergency_stop=False に上書きされる
                    logger.warning(
                        "State file parse error in clear_emergency_stop, "
                        "using safe default for circuit_closed preservation"
                    )
                    current = get_safe_default_state()

                # HF に基づいてモードを再計算
                hf = self._last_health_factor
                if hf is None:
                    mode = AaveOperationMode.NORMAL
                elif hf < self._hf_emergency_threshold:
                    # HF がまだ危険域なら HARD_STOP のまま（ただし emergency_stop は False）
                    mode = AaveOperationMode.HARD_STOP
                elif hf < self._hf_warning_threshold:
                    mode = AaveOperationMode.SAFE_MODE
                else:
                    mode = AaveOperationMode.NORMAL

                new_state = AaveSystemState(
                    emergency_stop=False,
                    mode=mode,
                    health_factor=hf,
                    last_update=self._now(None),
                    reason=None,
                    circuit_closed=current.circuit_closed,
                    stale_threshold_seconds=current.stale_threshold_seconds,
                )
                write_system_state(new_state)
                logger.debug(
                    "Cleared emergency stop in state file: mode=%s",
                    mode.value,
                )

            except Exception as exc:
                logger.warning("Failed to sync state file on clear_emergency_stop: %s", exc)

    def get_recent_events(self, limit: int = 100) -> List[MonitoringEvent]:
        """
        直近のイベントを新しい順に返す。
        """
        if limit <= 0:
            return []
        # deque は古い順に溜まるので、新しい順（降順）で返す
        events = list(self._events)
        return list(reversed(events[-limit:]))

    def get_events_in_range(
        self,
        from_timestamp: datetime,
        to_timestamp: datetime,
    ) -> List[MonitoringEvent]:
        """
        指定した時間範囲に含まれるイベントを返す。

        レポート集計用のユーティリティ。
        """
        start = self._normalize_bound(from_timestamp, _HEALTH_FACTOR_EPOCH)
        end = self._normalize_bound(
            to_timestamp,
            datetime.max.replace(tzinfo=timezone.utc),
        )
        return [event for event in self._events if start <= event.timestamp <= end]

    def get_health_factor_history(
        self,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None,
    ) -> List[Tuple[datetime, Optional[Decimal]]]:
        """
        ヘルスファクターの履歴を返す。

        - from_timestamp/to_timestamp を指定しなければ全件
        - None の値も含んだまま返す（集計側でフィルタ）
        """
        start = self._normalize_bound(from_timestamp, _HEALTH_FACTOR_EPOCH)
        end = self._normalize_bound(
            to_timestamp,
            datetime.max.replace(tzinfo=timezone.utc),
        )
        return [(ts, value) for ts, value in self._health_factors if start <= ts <= end]

    def get_status(self) -> AutomationStatus:
        """
        自動運用全体のステータスサマリを返す。
        """
        return AutomationStatus(
            is_trading_paused=bool(self._trading_paused),
            last_health_factor=self._last_health_factor,
            last_price_change_24h=self._last_price_change_24h,
            last_event_level=self._last_event_level,
            emergency_reason=self._emergency_reason,
            recent_events=list(self._events),
        )

    def build_dashboard_snapshot(
        self,
        *,
        lookback: timedelta = timedelta(hours=1),
        now: Optional[datetime] = None,
    ) -> DashboardSnapshot:
        """
        監視ダッシュボード向けのスナップショットを生成する。

        - 現在の AutomationStatus
        - 直近 lookback 期間に発生したメトリクスの集計結果

        をひとまとめにして返す。

        docs/08_automation_rules.md の「6. 監視メトリクス一覧」で定義された
        メトリクスID（latency_*, portfolio_value_change_1d_pct, aave_health_factor_current など）を
        前提にしており、新たなメトリクス種別は追加しない。
        """
        now_norm = self._now(now)
        period_start = now_norm - lookback

        events = self.get_events_in_range(period_start, now_norm)

        # メトリクスごとの値を集計
        metric_values: Dict[str, List[Decimal]] = {}
        metric_last: Dict[str, Decimal] = {}
        metric_units: Dict[str, Optional[str]] = {}

        for event in events:
            metric = event.metric
            if metric is None:
                continue

            mid = metric.metric_id
            value = metric.value

            metric_values.setdefault(mid, []).append(value)
            metric_last[mid] = value
            if mid not in metric_units or metric_units[mid] is None:
                metric_units[mid] = metric.unit

        metric_aggregates: Dict[str, MetricAggregate] = {}
        for mid, values in metric_values.items():
            count = len(values)
            min_v: Optional[Decimal] = min(values) if values else None
            max_v: Optional[Decimal] = max(values) if values else None
            last_v: Optional[Decimal] = metric_last.get(mid)

            if values:
                total = sum(values, Decimal("0"))
                avg_v: Optional[Decimal] = total / Decimal(count) if count > 0 else None
            else:
                avg_v = None

            metric_aggregates[mid] = MetricAggregate(
                metric_id=mid,
                unit=metric_units.get(mid),
                count=count,
                min=min_v,
                max=max_v,
                avg=avg_v,
                last=last_v,
            )

        status = self.get_status()
        return DashboardSnapshot(
            generated_at=now_norm,
            period_start=period_start,
            period_end=now_norm,
            status=status,
            metric_aggregates=metric_aggregates,
        )

    # ------------------------------------------------------------------
    # 公開 API: 並列ヘルスファクターチェック
    # ------------------------------------------------------------------
    async def check_health_factors_concurrent(
        self,
        wallets: List[str],
        get_health_factor_func: Callable[[str], Optional[Decimal]],
        *,
        max_concurrent: int = 10,
        timeout_seconds: float = 30.0,
    ) -> List[Optional[Decimal]]:
        """
        複数ウォレットのヘルスファクターを並列取得する。

        Pattern: python-async-patterns.md の「Pattern 1: Parallel RPC Calls」を適用。

        Args:
            wallets: チェック対象のウォレットアドレスリスト
            get_health_factor_func: 同期版のヘルスファクター取得関数
                                    (wallet_address) -> Optional[Decimal]
            max_concurrent: 最大同時実行数（RPC 負荷軽減）
            timeout_seconds: 各ウォレットのタイムアウト秒数

        Returns:
            List[Optional[Decimal]]: 各ウォレットのヘルスファクター
                                     エラー時は None（fail-closed）

        Note:
            - Web3.py は同期ライブラリのため asyncio.to_thread() でラップ
            - 1つのウォレットで失敗しても他は継続（partial success）
            - 全体の結果を record_health_factor() に渡すのは呼び出し側の責務
        """
        if not wallets:
            return []

        semaphore = asyncio.Semaphore(max_concurrent)

        async def check_wallet_safe(wallet: str) -> Optional[Decimal]:
            """個別ウォレットのヘルスファクター取得（タイムアウト付き）"""
            async with semaphore:
                try:
                    # 同期関数をスレッドプールで実行
                    hf = await asyncio.wait_for(
                        asyncio.to_thread(get_health_factor_func, wallet),
                        timeout=timeout_seconds,
                    )
                    logger.debug("Health factor for %s: %s", wallet, hf)
                    return hf
                except asyncio.TimeoutError:
                    logger.error(
                        "Timeout checking health factor for %s (%.1fs)",
                        wallet,
                        timeout_seconds,
                    )
                    return None  # Fail-closed
                except Exception as exc:
                    logger.error(
                        "Failed to check health factor for %s: %s",
                        wallet,
                        exc,
                    )
                    return None  # Fail-closed

        tasks = [check_wallet_safe(w) for w in wallets]
        results = await asyncio.gather(*tasks)

        logger.info(
            "Checked %d wallets concurrently: %d succeeded, %d failed",
            len(wallets),
            sum(1 for r in results if r is not None),
            sum(1 for r in results if r is None),
        )

        return list(results)

    async def check_all_positions_safe(
        self,
        get_health_factor_func: Callable[[], Optional[Decimal]],
    ) -> bool:
        """
        単一ポジションのヘルスファクターを確認し、安全かどうかを返す。

        Args:
            get_health_factor_func: 引数なしのヘルスファクター取得関数

        Returns:
            bool: True=安全（HF >= threshold または HF=None）, False=危険

        Note:
            - HF=None は「借入なし」として安全扱い
            - エラー発生時は False（fail-closed）
        """
        try:
            hf = await asyncio.to_thread(get_health_factor_func)

            if hf is None:
                # 借入なし = 安全
                logger.info("No debt position - considered safe")
                return True

            # ヘルスファクターを記録（state.json 同期含む）
            status = self.record_health_factor(hf)

            if status.is_emergency:
                logger.warning(
                    "Health factor %s is below emergency threshold",
                    hf,
                )
                return False

            return True

        except Exception as exc:
            logger.error("Failed to check position safety: %s", exc)
            return False  # Fail-closed
