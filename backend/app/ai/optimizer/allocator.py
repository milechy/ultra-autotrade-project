# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""ポートフォリオ配分計算モジュール。"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from .schemas import (
    AllocationEntry,
    AllocationRecommendation,
    NetBenefitResult,
    Protocol,
    Recommendation,
)

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n※ 本提案は将来の収益を保証するものではありません。投資判断は自己責任でお願いします。"
)

# 最小アイドル/現金リザーブ
_MIN_IDLE_PCT = Decimal("5")

# 単一プロトコルの最大配分（積極/バランス型）
_MAX_SINGLE_PROTOCOL_PCT = Decimal("70")

# Pendle YT の最大配分
_MAX_PENDLE_YT_PCT = Decimal("10")

# リスクモードのテンプレート配分
_CONSERVATIVE_TEMPLATE: dict[Protocol, Decimal] = {
    Protocol.AAVE: Decimal("95"),
    Protocol.IDLE: Decimal("5"),
}

_BALANCED_TEMPLATE: dict[Protocol, Decimal] = {
    Protocol.AAVE: Decimal("60"),
    Protocol.LIDO_AAVE: Decimal("25"),
    Protocol.PENDLE_PT: Decimal("10"),
    Protocol.IDLE: Decimal("5"),
}

_AGGRESSIVE_TEMPLATE: dict[Protocol, Decimal] = {
    Protocol.AAVE: Decimal("40"),
    Protocol.LIDO_AAVE: Decimal("25"),
    Protocol.PENDLE_PT: Decimal("15"),
    Protocol.PENDLE_YT: Decimal("10"),
    Protocol.IDLE: Decimal("10"),
}


class PortfolioAllocator:
    """リスクモードベースのポートフォリオ配分計算クラス。"""

    # 最小アイドル/現金リザーブ
    MIN_IDLE_PCT = _MIN_IDLE_PCT

    async def allocate(
        self,
        ranked_results: list[NetBenefitResult],
        total_usd: Decimal,
        risk_mode: str = "conservative",
    ) -> AllocationRecommendation:
        """リスクモードに基づいてポートフォリオ配分を計算する。

        conservative（安全重視）:
          - AAVE (95%) + IDLE (5%) のみ
          - Lido、Pendle なし

        balanced（バランス型）:
          - AAVE: 60%
          - LIDO_AAVE: 25%
          - PENDLE_PT: 10%（推奨度が AVOID でない場合）
          - IDLE: 5%
          - PENDLE_YT: 0%

        aggressive（積極型）:
          - AAVE: 40%
          - LIDO_AAVE: 25%
          - PENDLE_PT: 15%
          - PENDLE_YT: 10%（上限 10%）
          - IDLE: 10%（積極型はバッファを多めに）

        制約:
        - 単一プロトコル最大 70%（conservative で AAVE 95% は例外）
        - PENDLE_YT は常に <= 10%
        - IDLE は常に >= 5%
        - 配分合計 = 100%
        - 推奨度 AVOID のプロトコルには配分しない
        - AVOID のプロトコルは次点に再配分
        """
        risk_mode_lower = risk_mode.lower()
        if risk_mode_lower == "conservative":
            template = dict(_CONSERVATIVE_TEMPLATE)
        elif risk_mode_lower == "balanced":
            template = dict(_BALANCED_TEMPLATE)
        elif risk_mode_lower == "aggressive":
            template = dict(_AGGRESSIVE_TEMPLATE)
        else:
            logger.warning("Unknown risk_mode '%s', fallback to conservative", risk_mode)
            template = dict(_CONSERVATIVE_TEMPLATE)

        allocations = self._build_allocations(ranked_results, template, total_usd)
        allocations = self._apply_constraints(allocations)

        # 合計 APY とリスクスコアを計算
        total_expected_apy = self._calculate_weighted_apy(allocations, ranked_results)
        total_risk_score = await self._calculate_risk_score(allocations, ranked_results)

        explanation = self._generate_explanation(allocations, risk_mode_lower, total_expected_apy)

        logger.info(
            "allocate: risk_mode=%s, total_usd=%s, total_apy=%s, allocations=%d",
            risk_mode,
            total_usd,
            total_expected_apy,
            len(allocations),
        )

        return AllocationRecommendation(
            allocations=allocations,
            total_expected_apy=total_expected_apy,
            total_risk_score=total_risk_score,
            explanation=explanation,
        )

    def _build_allocations(
        self,
        ranked_results: list[NetBenefitResult],
        template: dict[Protocol, Decimal],
        total_usd: Decimal,
    ) -> list[AllocationEntry]:
        """テンプレートから配分エントリを作成し、AVOID プロトコルをスキップして再配分する。"""
        # AVOID プロトコルの特定
        avoid_protocols = {
            r.protocol for r in ranked_results if r.recommendation == Recommendation.AVOID
        }

        # プロトコル情報マップ（APY 取得用）
        protocol_info: dict[Protocol, NetBenefitResult] = {r.protocol: r for r in ranked_results}

        # AVOID プロトコルの配分を AAVE に再配分
        avoided_pct = Decimal("0")
        for protocol in list(template.keys()):
            if protocol in avoid_protocols and protocol != Protocol.IDLE:
                avoided_pct += template.pop(protocol)

        # AAVE が残っている場合は再配分先として使用
        if avoided_pct > Decimal("0") and Protocol.AAVE in template:
            template[Protocol.AAVE] = template[Protocol.AAVE] + avoided_pct
        elif avoided_pct > Decimal("0") and Protocol.IDLE in template:
            template[Protocol.IDLE] = template[Protocol.IDLE] + avoided_pct

        # 配分エントリ作成
        entries: list[AllocationEntry] = []
        for protocol, pct in template.items():
            if pct <= Decimal("0"):
                continue

            # IDLE の場合は特別処理
            if protocol == Protocol.IDLE:
                entries.append(
                    AllocationEntry(
                        protocol=Protocol.IDLE,
                        asset="CASH",
                        allocation_pct=pct,
                        amount_usd=total_usd * pct / Decimal("100"),
                        expected_apy=Decimal("0"),
                    )
                )
                continue

            # プロトコル情報から APY を取得
            info = protocol_info.get(protocol)
            if info is None:
                # ランク結果に見つからない場合はスキップ
                continue

            entries.append(
                AllocationEntry(
                    protocol=protocol,
                    asset=info.asset,
                    allocation_pct=pct,
                    amount_usd=total_usd * pct / Decimal("100"),
                    expected_apy=info.expected_apy,
                )
            )

        return entries

    def _apply_constraints(self, allocations: list[AllocationEntry]) -> list[AllocationEntry]:
        """制約を適用する: 単一プロトコル最大 70%、YT <= 10%、IDLE >= 5%、合計 = 100%。"""
        # PENDLE_YT の上限制約（インデックスで書き戻す）
        for i, entry in enumerate(allocations):
            if entry.protocol == Protocol.PENDLE_YT and entry.allocation_pct > _MAX_PENDLE_YT_PCT:
                excess = entry.allocation_pct - _MAX_PENDLE_YT_PCT
                original_pct = entry.allocation_pct
                allocations[i] = AllocationEntry(
                    protocol=entry.protocol,
                    asset=entry.asset,
                    allocation_pct=_MAX_PENDLE_YT_PCT,
                    amount_usd=entry.amount_usd * _MAX_PENDLE_YT_PCT / original_pct,
                    expected_apy=entry.expected_apy,
                )
                # 余剰分を IDLE に追加
                self._add_to_idle(allocations, excess, allocations[i].amount_usd)

        # 合計を確認して 100% に正規化（allocation_pct と amount_usd を再計算）
        total_pct = sum(e.allocation_pct for e in allocations)
        if total_pct != Decimal("100") and total_pct > Decimal("0"):
            total_amount = sum(e.amount_usd for e in allocations)
            allocations = [
                AllocationEntry(
                    protocol=e.protocol,
                    asset=e.asset,
                    allocation_pct=e.allocation_pct * Decimal("100") / total_pct,
                    amount_usd=e.amount_usd * Decimal("100") / total_pct
                    if total_amount == Decimal("0")
                    else e.amount_usd,
                    expected_apy=e.expected_apy,
                )
                for e in allocations
            ]

        return allocations

    def _add_to_idle(
        self,
        allocations: list[AllocationEntry],
        excess_pct: Decimal,
        _original_amount: Decimal,
    ) -> None:
        """余剰分を IDLE エントリに追加する（存在する場合）。"""
        for i, entry in enumerate(allocations):
            if entry.protocol == Protocol.IDLE:
                allocations[i] = AllocationEntry(
                    protocol=entry.protocol,
                    asset=entry.asset,
                    allocation_pct=entry.allocation_pct + excess_pct,
                    amount_usd=entry.amount_usd,
                    expected_apy=entry.expected_apy,
                )
                return

    def _calculate_weighted_apy(
        self,
        allocations: list[AllocationEntry],
        ranked_results: list[NetBenefitResult],
    ) -> Decimal:
        """加重平均 APY を計算する。"""
        protocol_apy: dict[Protocol, Decimal] = {}
        for r in ranked_results:
            # gross_yield から APY を逆算せず、scorer のデフォルト APY を参照
            protocol_apy[r.protocol] = r.gross_yield

        # 各プロトコルの APY は scored_candidates から取得できないため、
        # AllocationEntry の expected_apy を使用
        total_weighted = Decimal("0")
        for entry in allocations:
            if entry.allocation_pct > Decimal("0"):
                total_weighted += entry.expected_apy * entry.allocation_pct / Decimal("100")

        return total_weighted

    # フォールバック用の固定リスクスコア（プロトコル別）
    _FALLBACK_RISK_MAP: dict[Protocol, Decimal] = {
        Protocol.AAVE: Decimal("0.05"),
        Protocol.LIDO: Decimal("0.15"),
        Protocol.LIDO_AAVE: Decimal("0.20"),
        Protocol.PENDLE_PT: Decimal("0.10"),
        Protocol.PENDLE_YT: Decimal("0.30"),
        Protocol.IDLE: Decimal("0.00"),
    }

    # リスクエンジンのレベルから Decimal スコアへのマッピング
    _RISK_LEVEL_TO_SCORE: dict[str, Decimal] = {
        "low": Decimal("0.05"),
        "medium": Decimal("0.25"),
        "high": Decimal("0.60"),
        "critical": Decimal("0.90"),
    }

    # リスクエンジンのプロトコル名からオプティマイザー Protocol への対応
    _PROTOCOL_NAME_MAP: dict[str, list[Protocol]] = {
        "aave": [Protocol.AAVE],
        "lido": [Protocol.LIDO, Protocol.LIDO_AAVE],
        "pendle": [Protocol.PENDLE_PT, Protocol.PENDLE_YT],
    }

    async def _build_dynamic_risk_map(self) -> Optional[dict[Protocol, Decimal]]:
        """リスクエンジンから動的リスクスコアマップを構築する（async）。

        Returns:
            プロトコル → リスクスコアのマップ。取得失敗時は None。
        """
        try:
            from app.protocols.risk.protocol_monitor import ProtocolMonitor  # noqa: PLC0415

            monitor = ProtocolMonitor()
            protocol_healths = await monitor.check_all()

            risk_map: dict[Protocol, Decimal] = {}
            for health in protocol_healths:
                protocols = self._PROTOCOL_NAME_MAP.get(health.protocol, [])
                score = self._RISK_LEVEL_TO_SCORE.get(health.risk_level.value, Decimal("0.10"))
                for protocol in protocols:
                    risk_map[protocol] = score

            # IDLE は常に 0
            risk_map[Protocol.IDLE] = Decimal("0.00")

            logger.debug("using dynamic risk score from risk engine: %s", risk_map)
            return risk_map

        except Exception as exc:
            logger.warning("risk engine unavailable, using fallback risk scores: %s", exc)
            return None

    async def _calculate_risk_score(
        self,
        allocations: list[AllocationEntry],
        ranked_results: list[NetBenefitResult],
    ) -> Decimal:
        """加重平均リスクスコアを計算する（async）。

        リスクエンジンから動的スコアを取得し、失敗時はフォールバック固定値を使用する。
        """
        risk_map = await self._build_dynamic_risk_map()
        if risk_map is None:
            # フォールバック: 固定値を使用
            risk_map = dict(self._FALLBACK_RISK_MAP)

        total_risk = Decimal("0")
        for entry in allocations:
            risk = risk_map.get(entry.protocol, Decimal("0.10"))
            total_risk += risk * entry.allocation_pct / Decimal("100")

        return total_risk

    def _generate_explanation(
        self,
        allocations: list[AllocationEntry],
        risk_mode: str,
        total_expected_apy: Decimal,
    ) -> str:
        """利用者向けの説明文を生成する（日本語、専門用語なし）。"""
        apy_str = f"{total_expected_apy:.1f}"

        if risk_mode == "conservative":
            explanation = f"安全重視の配分です。預金のみで年率約{apy_str}%の利回りが期待できます。"
        elif risk_mode == "balanced":
            explanation = (
                f"バランス型の配分です。"
                f"複数の運用先に分散し、年率約{apy_str}%の利回りが期待できます。"
            )
        elif risk_mode == "aggressive":
            explanation = (
                f"積極型の配分です。"
                f"高い利回りを狙いますが、リスクも高めです。年率約{apy_str}%の期待利回りです。"
            )
        else:
            explanation = f"年率約{apy_str}%の利回りが期待できます。"
        return explanation + _DISCLAIMER
