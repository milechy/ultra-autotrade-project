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

from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Deque, Dict, List, Optional, Sequence  # ← Deque を追加

from .schemas import (
    AlertLevel,
    AutomationStatus,
    ComponentType,
    HealthFactorStatus,
    LatencyRecord,
    MetricPoint,
    MonitoringEvent,
    TradeActivityRecord,
    DashboardSnapshot,   # ← 追加
    MetricAggregate,     # ← 追加
)

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
    ) -> None:
        # 閾値
        self._latency_warning_threshold_s = float(latency_warning_threshold_s)
        self._latency_alert_threshold_s = float(latency_alert_threshold_s)
        self._hf_warning_threshold = Decimal(healthfactor_warning_threshold)
        self._hf_emergency_threshold = Decimal(healthfactor_emergency_threshold)
        self._price_change_alert_threshold_pct = float(price_change_alert_threshold_pct)

        # 状態
        self._events: Deque[MonitoringEvent] = deque(maxlen=max_events)
        self._latencies: Deque[LatencyRecord] = deque(maxlen=max_latency_records)
        self._trades: Deque[TradeActivityRecord] = deque(maxlen=max_trade_records)
        # ヘルスファクターの履歴（レポート集計用）
        self._health_factors: Deque[tuple[datetime, Optional[Decimal]]] = deque(
            maxlen=max_healthfactor_records
        )

        self._trading_paused: bool = False
        self._emergency_reason: Optional[str] = None
        self._last_health_factor: Optional[Decimal] = None
        self._last_price_change_24h: Optional[float] = None
        self._last_event_level: AlertLevel = AlertLevel.INFO

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
            float(duration.total_seconds())
            if isinstance(duration, timedelta)
            else float(duration)
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
        - ヘルスファクター < 1.8 → 警告
        - ヘルスファクター < 1.6 → 緊急停止
        """
        now = self._now(at)
        self._last_health_factor = value
        self._health_factors.append((now, value))

        if value is None:
            status = HealthFactorStatus(
                current=None,
                level=AlertLevel.INFO,
                is_emergency=False,
            )
            return status

        level: AlertLevel = AlertLevel.INFO
        is_emergency = False

        if value < self._hf_emergency_threshold:
            level = AlertLevel.EMERGENCY
            is_emergency = True
            self._trading_paused = True
            if self._emergency_reason is None:
                self._emergency_reason = (
                    f"health factor {value} below emergency threshold "
                    f"{self._hf_emergency_threshold}"
                )
            event = MonitoringEvent(
                timestamp=now,
                component=ComponentType.AAVE,
                level=level,
                code="HF_BELOW_EMERGENCY",
                message=self._emergency_reason,
            )
            # メトリクス情報を添付
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
            event = MonitoringEvent(
                timestamp=now,
                component=ComponentType.AAVE,
                level=level,
                code="HF_BELOW_WARNING",
                message=(
                    f"health factor {value} below warning threshold "
                    f"{self._hf_warning_threshold}"
                ),
            )
            # メトリクス情報を添付
            event.metric = MetricPoint(
                metric_id="aave_health_factor_current",
                value=value,
                unit="ratio",
                labels={"component": "AAVE"},
                recorded_at=now,
            )
            self._append_event(event)

        status = HealthFactorStatus(
            current=value,
            level=level,
            is_emergency=is_emergency,
        )
        return status

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
            # メトリクス情報を添付
            event.metric = MetricPoint(
                metric_id="portfolio_value_change_1d_pct",
                value=Decimal(str(percent_change)),
                unit="percent",
                labels={"window": "24h"},
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
        return self._append_event(event)

    def clear_emergency_stop(self) -> None:
        """
        緊急停止状態を解除する。

        自動解除は危険なので、基本的には運用者が明示的に呼び出す想定。
        """
        self._trading_paused = False
        self._emergency_reason = None

    def get_recent_events(self, limit: int = 100) -> List[MonitoringEvent]:
        """
        直近のイベントを新しい順に返す。
        """
        if limit <= 0:
            return []
        # deque は古い順に並ぶので、逆順にしてから limit をかける
        events: Sequence[MonitoringEvent] = list(self._events)[-limit:]
        return list(events)[-limit:]

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
        return [
            event
            for event in self._events
            if start <= event.timestamp <= end
        ]

    def get_health_factor_history(
        self,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None,
    ) -> List[tuple[datetime, Optional[Decimal]]]:
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
        return [
            (ts, value)
            for ts, value in self._health_factors
            if start <= ts <= end
        ]

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
                avg_v: Optional[Decimal] = (
                    total / Decimal(count) if count > 0 else None
                )
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
