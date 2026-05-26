# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/oracle_monitor.py

"""
Aave 主要資産 (USDC / WETH 等) の Chainlink oracle 価格・staleness を監視し、
異常検知時に MonitoringService.activate_emergency_stop を自動発火するモジュール。

設計方針 (Asana 1215080599381152):
- 既存 ``app.aave.oracle_checker.check_oracle_staleness`` を呼び出して staleness /
  価格乖離を判定 (重複実装しない)
- 既存 ``MonitoringService.activate_emergency_stop`` を経由して停止 + Slack 通知を
  共通化 (本モジュールから直接通知しない)
- 配線 (scheduler / router / agents.py) は本 PR では行わず、別 PR で提案する

False positive 抑制:
- 既定では oracle 異常 AND HF<warning 閾値の AND 条件でのみ emergency_stop 発火
- ただし「極端な異常」(age > extreme_staleness_threshold_seconds または
  deviation > extreme_deviation_pct) の場合は HF 状態に関わらず発火 (fail-safe)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from app.aave.oracle_checker import OracleCheckResult, check_oracle_staleness
from app.automation.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)

DEFAULT_STALENESS_THRESHOLD_SECONDS = 3600
DEFAULT_DEVIATION_THRESHOLD_PCT = Decimal("10")
DEFAULT_EXTREME_STALENESS_THRESHOLD_SECONDS = 24 * 3600
DEFAULT_EXTREME_DEVIATION_PCT = Decimal("30")
DEFAULT_HF_GUARD_THRESHOLD = Decimal("1.8")


@dataclass(frozen=True)
class OracleFeedConfig:
    """
    監視対象の Chainlink price feed 設定。

    name: USDC / WETH などのシンボル
    feed_address: Chainlink AggregatorV3 のアドレス
    rpc_url: 接続先 RPC エンドポイント (Polygon / Base / Arbitrum 等)
    """

    name: str
    feed_address: str
    rpc_url: str


@dataclass
class OracleMonitorReport:
    """1 回分の oracle ポーリング結果。"""

    feed_results: Dict[str, OracleCheckResult] = field(default_factory=dict)
    fetch_failures: List[str] = field(default_factory=list)
    anomaly_detected: bool = False
    emergency_triggered: bool = False
    reasons: List[str] = field(default_factory=list)


class OracleMonitor:
    """
    Chainlink oracle の状態を定期取得し、異常時に emergency_stop を発火する。

    Note:
        - 価格乖離判定は前回ポーリング時の値を内部キャッシュして比較する
          (oracle_checker.check_oracle_staleness の previous_price 引数に渡す)
        - 通知は MonitoringService.activate_emergency_stop 内の既存実装に委譲する
        - 配線 (scheduler) は本クラスを呼び出す側で行う (別 PR 想定)
    """

    def __init__(
        self,
        monitoring_service: MonitoringService,
        feeds: Sequence[OracleFeedConfig],
        *,
        staleness_threshold_seconds: int = DEFAULT_STALENESS_THRESHOLD_SECONDS,
        deviation_threshold_pct: Decimal = DEFAULT_DEVIATION_THRESHOLD_PCT,
        extreme_staleness_threshold_seconds: int = (DEFAULT_EXTREME_STALENESS_THRESHOLD_SECONDS),
        extreme_deviation_pct: Decimal = DEFAULT_EXTREME_DEVIATION_PCT,
        hf_guard_threshold: Decimal = DEFAULT_HF_GUARD_THRESHOLD,
        require_hf_confirmation: bool = True,
    ) -> None:
        if not feeds:
            raise ValueError("OracleMonitor requires at least one feed")
        if staleness_threshold_seconds <= 0:
            raise ValueError("staleness_threshold_seconds must be positive")
        if deviation_threshold_pct <= 0:
            raise ValueError("deviation_threshold_pct must be positive")
        if extreme_staleness_threshold_seconds < staleness_threshold_seconds:
            raise ValueError(
                "extreme_staleness_threshold_seconds must be >= staleness_threshold_seconds"
            )
        if extreme_deviation_pct < deviation_threshold_pct:
            raise ValueError("extreme_deviation_pct must be >= deviation_threshold_pct")

        self._monitoring = monitoring_service
        self._feeds = list(feeds)
        self._staleness_threshold_seconds = staleness_threshold_seconds
        self._deviation_threshold_pct = Decimal(deviation_threshold_pct)
        self._extreme_staleness_threshold_seconds = extreme_staleness_threshold_seconds
        self._extreme_deviation_pct = Decimal(extreme_deviation_pct)
        self._hf_guard_threshold = Decimal(hf_guard_threshold)
        self._require_hf_confirmation = bool(require_hf_confirmation)

        self._previous_prices: Dict[str, Decimal] = {}

    @property
    def feeds(self) -> List[OracleFeedConfig]:
        return list(self._feeds)

    def check_once(self) -> OracleMonitorReport:
        """
        全フィードを 1 回ポーリングし、判定結果と緊急停止発火状況を返す。

        emergency_stop を発火する条件:
          1. ``require_hf_confirmation=False`` で oracle 異常が 1 件以上
          2. ``require_hf_confirmation=True`` のとき、oracle 異常 1 件以上 かつ
             直近 HF が None でなく ``hf_guard_threshold`` 未満
          3. 上記に関わらず、極端な異常 (age > extreme_staleness または
             deviation > extreme_deviation_pct) が 1 件でもあれば発火 (fail-safe)
        """
        report = OracleMonitorReport()

        for feed in self._feeds:
            previous_price = self._previous_prices.get(feed.name)
            try:
                result = check_oracle_staleness(
                    feed_address=feed.feed_address,
                    rpc_url=feed.rpc_url,
                    staleness_threshold_seconds=self._staleness_threshold_seconds,
                    deviation_threshold_pct=self._deviation_threshold_pct,
                    previous_price=previous_price,
                )
            except Exception as exc:
                logger.warning(
                    "[oracle_monitor] check_oracle_staleness raised for feed=%s: %s",
                    feed.name,
                    exc,
                )
                report.fetch_failures.append(feed.name)
                continue

            if result is None:
                report.fetch_failures.append(feed.name)
                continue

            report.feed_results[feed.name] = result

            # 次回ポーリング時の deviation 比較に使う最新価格をキャッシュ
            if result.price is not None:
                self._previous_prices[feed.name] = result.price

            if result.should_hold:
                report.anomaly_detected = True
                report.reasons.append(f"{feed.name}: " + "; ".join(result.reasons))

        extreme_reasons = self._collect_extreme_reasons(report.feed_results)
        if extreme_reasons:
            report.anomaly_detected = True
            report.reasons.extend(extreme_reasons)

        if not report.anomaly_detected:
            return report

        if extreme_reasons:
            self._trigger_emergency(report, mode="extreme")
            return report

        if not self._require_hf_confirmation:
            self._trigger_emergency(report, mode="oracle_only")
            return report

        hf = self._get_last_health_factor()
        if hf is not None and hf < self._hf_guard_threshold:
            self._trigger_emergency(
                report,
                mode=f"oracle_and_hf(hf={hf})",
            )
        else:
            logger.warning(
                "[oracle_monitor] Oracle anomaly detected but HF=%s is healthy "
                "(threshold=%s); emergency_stop suppressed by AND policy. reasons=%s",
                hf,
                self._hf_guard_threshold,
                report.reasons,
            )

        return report

    async def monitor_loop(self, interval_seconds: int = 60) -> None:
        """
        ``interval_seconds`` ごとに ``check_once`` を呼び出す常駐ループ。

        個別の ``check_once`` 失敗は監視を停止させず、次回間隔まで待機する。
        """
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        logger.info(
            "[oracle_monitor] Starting monitor loop (feeds=%d, interval=%ds)",
            len(self._feeds),
            interval_seconds,
        )
        while True:
            try:
                self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "[oracle_monitor] check_once raised unexpectedly: %s",
                    exc,
                )
            await asyncio.sleep(interval_seconds)

    def _collect_extreme_reasons(
        self,
        feed_results: Dict[str, OracleCheckResult],
    ) -> List[str]:
        reasons: List[str] = []
        for name, result in feed_results.items():
            if (
                result.age_seconds is not None
                and result.age_seconds > self._extreme_staleness_threshold_seconds
            ):
                reasons.append(
                    f"{name}: extreme staleness age={result.age_seconds}s > "
                    f"{self._extreme_staleness_threshold_seconds}s"
                )
            if (
                result.deviation_pct is not None
                and result.deviation_pct > self._extreme_deviation_pct
            ):
                reasons.append(
                    f"{name}: extreme deviation {result.deviation_pct:.2f}% > "
                    f"{self._extreme_deviation_pct}%"
                )
        return reasons

    def _get_last_health_factor(self) -> Optional[Decimal]:
        status = self._monitoring.get_status()
        return status.last_health_factor

    def _trigger_emergency(self, report: OracleMonitorReport, *, mode: str) -> None:
        from app.automation.schemas import ComponentType  # noqa: PLC0415

        reason = "Aave oracle anomaly [{}]: {}".format(
            mode,
            " | ".join(report.reasons) if report.reasons else "unspecified",
        )
        logger.error("[oracle_monitor] Activating emergency_stop: %s", reason)
        try:
            self._monitoring.activate_emergency_stop(
                reason=reason,
                component=ComponentType.AAVE,
            )
            report.emergency_triggered = True
        except Exception as exc:
            logger.exception(
                "[oracle_monitor] activate_emergency_stop failed: %s",
                exc,
            )
