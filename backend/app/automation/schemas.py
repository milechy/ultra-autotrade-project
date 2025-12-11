# backend/app/automation/schemas.py

"""
監視・アラート・緊急停止まわりの共通スキーマ定義。

Phase5 で導入する MonitoringService / ReportingService が利用するデータ構造をまとめる。
docs/08_automation_rules.md / 13_security_design.md / 15_rollback_procedures.md を前提に設計。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional  # ★ List を追加

from pydantic import BaseModel, Field


class AlertLevel(str, Enum):
    """
    監視イベントの重要度レベル。

    - WARNING: しきい値超過だが、即時停止までは不要
    - ALERT: 強い注意が必要。手動確認推奨
    - CRITICAL: 重大な異常。運用継続は危険
    - EMERGENCY: 緊急停止状態
    """

    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class ComponentType(str, Enum):
    """
    監視対象コンポーネントの種別。
    """

    NOTION = "notion"
    AI = "ai"
    OCTOBOT = "octobot"
    AAVE = "aave"
    SYSTEM = "system"
    BACKUP = "backup"
    REPORT = "report"


class MetricPoint(BaseModel):
    """単一メトリクスのスナップショット。

    docs/08_automation_rules.md の「6. 監視メトリクス一覧」で定義した
    メトリクスID（例: backend_http_latency_p95_ms）と、その値を表現する。
    """

    metric_id: str = Field(
        ...,
        description="メトリクスの論理ID（例: backend_http_latency_p95_ms）",
    )
    value: Decimal = Field(
        ...,
        description="測定値。Decimal として扱うことで HF などと整合性を保つ。",
    )
    unit: Optional[str] = Field(
        None,
        description="単位（例: s, ms, percent, ratio）。不要な場合は None。",
    )
    labels: Dict[str, str] = Field(
        default_factory=dict,
        description="component, endpoint などのラベル情報",
    )
    recorded_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="メトリクスが記録されたUTC時刻",
    )


class MonitoringEvent(BaseModel):
    """
    監視イベント 1件分。

    後続のレポート生成・通知でそのまま利用できるよう、最低限のメタ情報を持たせる。
    """

    timestamp: datetime = Field(..., description="イベント発生時刻（UTC推奨）")
    component: ComponentType = Field(..., description="イベントが発生したコンポーネント")
    level: AlertLevel = Field(..., description="イベントの重要度")
    code: str = Field(..., description="機械可読なイベントコード（例: LATENCY_SLOW, HF_BELOW_16）")
    message: str = Field(..., description="人間向けのメッセージ（センシティブ情報は含めないこと）")
    metric: Optional[MetricPoint] = Field(
        default=None,
        description="しきい値判定の原因となったメトリクス情報（あれば）",
    )


class LatencyRecord(BaseModel):
    """
    死活監視用の応答時間記録。
    """

    component: ComponentType = Field(..., description="対象コンポーネント")
    timestamp: datetime = Field(..., description="計測時刻")
    duration_ms: int = Field(..., ge=0, description="応答時間（ミリ秒）")


class TradeActivityRecord(BaseModel):
    """
    過剰取引監視用のアクティビティ記録。
    """

    component: ComponentType = Field(..., description="対象コンポーネント（通常は OCTOBOT / AAVE）")
    action: str = Field(..., description="BUY/SELL/HOLD などのアクション種別（文字列表現）")
    timestamp: datetime = Field(..., description="アクション実行時刻")


class HealthFactorStatus(BaseModel):
    """
    ヘルスファクター監視の判定結果。
    """

    current: Optional[Decimal] = Field(
        None,
        description="現在のヘルスファクター。取得できなかった場合は None。",
    )
    level: AlertLevel = Field(
        ...,
        description="現在のヘルスファクターに基づく重要度レベル。",
    )
    is_emergency: bool = Field(
        ...,
        description="緊急停止レベルかどうか。",
    )


class AutomationStatus(BaseModel):
    """
    自動運用基盤全体のステータスサマリ。

    - 緊急停止状態かどうか
    - 直近のヘルスファクター・価格変動
    - 直近のイベント一覧
    をまとめて返す。
    """

    is_trading_paused: bool = Field(..., description="現在トレードが停止状態かどうか")
    last_health_factor: Optional[Decimal] = Field(
        None, description="最後に観測したヘルスファクター"
    )
    last_price_change_24h: Optional[float] = Field(
        None,
        description="最後に観測した24時間価格変動率（%）。正の値が上昇。",
    )
    last_event_level: AlertLevel = Field(
        AlertLevel.INFO,
        description="最後に発生したイベントの重要度レベル。",
    )
    emergency_reason: Optional[str] = Field(
        None,
        description="緊急停止中の場合、その理由（ログ・通知用）。",
    )
    recent_events: List[MonitoringEvent] = Field(
        default_factory=list,
        description="最近のイベント。件数は MonitoringService 側で制御する。",
    )


# ---------------------------------------------------------------------------
# レポート用スキーマ
# ---------------------------------------------------------------------------

class MetricAggregate(BaseModel):
    """
    単一メトリクスIDに対する集計値。

    - MonitoringEvent.metric やヘルスファクター履歴から集計される
    - ダッシュボードやレポートの「パネル1つぶん」に対応するイメージ
    """

    metric_id: str = Field(
        ...,
        description="集計対象のメトリクスID（例: latency_system_s, portfolio_value_change_1d_pct）",
    )
    unit: Optional[str] = Field(
        None,
        description="メトリクスの単位（例: s, percent, ratio）。未設定の場合は None。",
    )
    count: int = Field(
        ...,
        description="対象期間中に観測されたサンプル数。",
    )
    min: Optional[Decimal] = Field(
        None,
        description="対象期間中に観測された最小値（観測がなければ None）。",
    )
    max: Optional[Decimal] = Field(
        None,
        description="対象期間中に観測された最大値（観測がなければ None）。",
    )
    avg: Optional[Decimal] = Field(
        None,
        description="対象期間中の平均値（観測がなければ None）。",
    )
    last: Optional[Decimal] = Field(
        None,
        description="対象期間中に最後に観測された値（観測がなければ None）。",
    )


class DashboardSnapshot(BaseModel):
    """
    ダッシュボード向けのスナップショット。

    MonitoringService の現在ステータスと、
    直近一定期間のメトリクス集計結果をひとまとめにしたもの。
    """

    generated_at: datetime = Field(
        ...,
        description="スナップショット生成時刻（UTC推奨）。",
    )
    period_start: datetime = Field(
        ...,
        description="このスナップショットが集計対象とする期間の開始時刻。",
    )
    period_end: datetime = Field(
        ...,
        description="このスナップショットが集計対象とする期間の終了時刻。",
    )
    status: AutomationStatus = Field(
        ...,
        description="現在の自動運用ステータス（緊急停止フラグや直近イベントなど）。",
    )
    metric_aggregates: Dict[str, MetricAggregate] = Field(
        default_factory=dict,
        description="メトリクスIDごとの集計結果。キーは metric_id。",
    )
class ReportPeriod(str, Enum):
    """
    レポート対象期間の種別。

    - DAILY: 当日分
    - WEEKLY: 直近7日分
    """

    DAILY = "daily"
    WEEKLY = "weekly"


class AutomationReportSummary(BaseModel):
    """
    監視イベントとヘルスファクター履歴から集計したレポートサマリ。

    実際の Notion/通知連携は別モジュールがこのモデルをもとに行う想定。
    """

    period: ReportPeriod = Field(..., description="レポート対象期間の種別")
    from_timestamp: datetime = Field(..., description="レポート対象期間の開始時刻")
    to_timestamp: datetime = Field(..., description="レポート対象期間の終了時刻（通常は now）")

    total_events: int = Field(..., description="対象期間中の全イベント件数")
    info_count: int = Field(..., description="INFO レベルのイベント数")
    warning_count: int = Field(..., description="WARNING レベルのイベント数")
    alert_count: int = Field(..., description="ALERT レベルのイベント数")
    critical_count: int = Field(..., description="CRITICAL レベルのイベント数")
    emergency_count: int = Field(..., description="EMERGENCY レベルのイベント数")

    emergency_occurred: bool = Field(
        ...,
        description="対象期間中に EMERGENCY レベルのイベントが1つでも発生したかどうか。",
    )

    min_health_factor: Optional[Decimal] = Field(
        None,
        description="対象期間中に観測されたヘルスファクターの最小値（観測がなければ None）。",
    )
    max_health_factor: Optional[Decimal] = Field(
        None,
        description="対象期間中に観測されたヘルスファクターの最大値（観測がなければ None）。",
    )
    last_health_factor: Optional[Decimal] = Field(
        None,
        description="対象期間中に最後に観測されたヘルスファクター（観測がなければ None）。",
    )

    metric_aggregates: Dict[str, MetricAggregate] = Field(
        default_factory=dict,
        description=(
            "対象期間中に観測されたメトリクスごとの集計結果。"
            "キーは metric_id。ダッシュボードや外部可観測性ツールから再利用しやすい形式。"
        ),
    )

    notes: Optional[str] = Field(
        None,
        description="人間向けの簡易コメント。将来的に AI による文章生成に置き換え可能。",
    )