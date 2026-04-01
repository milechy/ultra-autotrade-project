# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""マルチプロトコル複合リスク評価モジュール。"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from .maturity_manager import MaturityManager
from .peg_monitor import PegMonitor
from .protocol_monitor import ProtocolMonitor
from .schemas import (
    CompoundRiskAssessment,
    MaturityAlert,
    PegStatus,
    ProtocolHealth,
    RiskLevel,
)

logger = logging.getLogger(__name__)

# リスクスコア重み定数
_PROTOCOL_SCORES: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 5,
    RiskLevel.HIGH: 15,
    RiskLevel.CRITICAL: 40,
}
_PEG_SCORES: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 5,
    RiskLevel.HIGH: 15,
    RiskLevel.CRITICAL: 30,
}
_MATURITY_SCORES: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 5,
    RiskLevel.HIGH: 15,
    RiskLevel.CRITICAL: 30,
}


class CompoundRiskAssessor:
    """全プロトコルにまたがる複合リスクを評価するクラス。"""

    def __init__(
        self,
        protocol_monitor: Optional[ProtocolMonitor] = None,
        peg_monitor: Optional[PegMonitor] = None,
        maturity_manager: Optional[MaturityManager] = None,
    ) -> None:
        """初期化。

        Args:
            protocol_monitor: プロトコル監視インスタンス（None の場合は生成）
            peg_monitor: ペグ監視インスタンス（None の場合は生成）
            maturity_manager: 満期管理インスタンス（None の場合は生成）
        """
        self._protocol_monitor = protocol_monitor or ProtocolMonitor()
        self._peg_monitor = peg_monitor or PegMonitor()
        self._maturity_manager = maturity_manager or MaturityManager()

    async def assess(self, market_addresses: list[str] | None = None) -> CompoundRiskAssessment:
        """複合リスク評価を実行する。

        処理フロー:
        1. 全プロトコルヘルスチェック
        2. ペグ状態確認
        3. 満期アラート確認
        4. 複合リスクスコア計算
        5. 推奨アクション生成
        6. 避難判定

        Args:
            market_addresses: 確認するマーケットアドレス（None でデフォルト使用）

        Returns:
            CompoundRiskAssessment
        """
        logger.info("assess: 複合リスク評価開始")

        protocol_risks = await self._protocol_monitor.check_all()
        peg_status = await self._peg_monitor.get_peg_status()
        maturity_alerts = await self._maturity_manager.check_maturities(market_addresses)

        risk_score = self.calculate_risk_score(protocol_risks, peg_status, maturity_alerts)
        overall_risk = self._determine_overall_risk(risk_score)
        recommendations = self._generate_recommendations(
            overall_risk, protocol_risks, peg_status, maturity_alerts
        )

        # 避難判定
        should_evacuate = False
        evacuation_reason: Optional[str] = None

        if any(p.risk_level == RiskLevel.CRITICAL for p in protocol_risks):
            should_evacuate = True
            critical_protocols = [
                p.protocol for p in protocol_risks if p.risk_level == RiskLevel.CRITICAL
            ]
            evacuation_reason = (
                f"プロトコルで緊急リスクが検知されました: {', '.join(critical_protocols)}"
            )

        if peg_status.risk_level == RiskLevel.CRITICAL:
            should_evacuate = True
            evacuation_reason = evacuation_reason or "価格連動性に深刻な乖離が発生しています"

        if any(a.risk_level == RiskLevel.CRITICAL for a in maturity_alerts):
            should_evacuate = True
            evacuation_reason = evacuation_reason or "運用商品の期限が今すぐ迫っています"

        if risk_score >= Decimal("80"):
            should_evacuate = True
            evacuation_reason = (
                evacuation_reason or f"リスクスコアが危険域に達しました（{risk_score}）"
            )

        # エクスポージャー合計（PoC: プロトコル TVL の合算）
        total_exposure_usd = sum(p.tvl_usd for p in protocol_risks)

        logger.info(
            "assess 完了: overall_risk=%s, score=%s, should_evacuate=%s",
            overall_risk.value,
            risk_score,
            should_evacuate,
        )

        return CompoundRiskAssessment(
            overall_risk=overall_risk,
            protocol_risks=protocol_risks,
            peg_status=peg_status,
            maturity_alerts=maturity_alerts,
            total_exposure_usd=total_exposure_usd,
            risk_score=risk_score,
            recommendations=recommendations,
            should_evacuate=should_evacuate,
            evacuation_reason=evacuation_reason,
        )

    def calculate_risk_score(
        self,
        protocol_risks: list[ProtocolHealth],
        peg_status: Optional[PegStatus],
        maturity_alerts: list[MaturityAlert],
    ) -> Decimal:
        """複合リスクスコアを計算する（0-100）。

        プロトコルコンポーネント（最大 40）:
            各プロトコルのスコアを取得し最大値を採用。
            LOW=0, MEDIUM=5, HIGH=15, CRITICAL=40

        ペグコンポーネント（最大 30）:
            LOW=0, MEDIUM=5, HIGH=15, CRITICAL=30

        満期コンポーネント（最大 30）:
            各満期アラートのスコアの最大値を採用。
            LOW=0, MEDIUM=5, HIGH=15, CRITICAL=30

        いずれかのコンポーネントが CRITICAL の場合 → 最低 80 に切り上げ
        合計スコアは 0〜100 の範囲にクランプ。
        """
        # プロトコルコンポーネント
        protocol_score = 0
        for p in protocol_risks:
            s = _PROTOCOL_SCORES.get(p.risk_level, 0)
            if s > protocol_score:
                protocol_score = s

        # ペグコンポーネント
        peg_score = 0
        if peg_status is not None:
            peg_score = _PEG_SCORES.get(peg_status.risk_level, 0)

        # 満期コンポーネント
        maturity_score = 0
        for a in maturity_alerts:
            s = _MATURITY_SCORES.get(a.risk_level, 0)
            if s > maturity_score:
                maturity_score = s

        total = protocol_score + peg_score + maturity_score

        # CRITICAL 検知時は最低 80 に切り上げ
        has_critical = (
            any(p.risk_level == RiskLevel.CRITICAL for p in protocol_risks)
            or (peg_status is not None and peg_status.risk_level == RiskLevel.CRITICAL)
            or any(a.risk_level == RiskLevel.CRITICAL for a in maturity_alerts)
        )
        if has_critical and total < 80:
            total = 80

        # 0-100 クランプ
        total = max(0, min(100, total))
        return Decimal(str(total))

    def _determine_overall_risk(self, risk_score: Decimal) -> RiskLevel:
        """リスクスコアを全体リスクレベルに変換する。

        0-20 → LOW
        21-40 → MEDIUM
        41-70 → HIGH
        71-100 → CRITICAL
        """
        if risk_score <= Decimal("20"):
            return RiskLevel.LOW
        if risk_score <= Decimal("40"):
            return RiskLevel.MEDIUM
        if risk_score <= Decimal("70"):
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def _generate_recommendations(
        self,
        overall_risk: RiskLevel,
        protocol_risks: list[ProtocolHealth],
        peg_status: Optional[PegStatus],
        maturity_alerts: list[MaturityAlert],
    ) -> list[str]:
        """人が読みやすい推奨アクションを日本語で生成する（専門用語なし）。

        LOW: 安全メッセージのみ。
        MEDIUM: 関連する警告を追加。
        HIGH: リスク増加の警告と具体的アドバイス。
        CRITICAL: 緊急対応メッセージ。
        """
        recommendations: list[str] = []

        if overall_risk == RiskLevel.LOW:
            recommendations.append("現在のポジションは安全です。特に対応は不要です。")
            return recommendations

        if overall_risk == RiskLevel.CRITICAL:
            recommendations.append("緊急対応が必要です。安全な資産への移動を強く推奨します。")

        if overall_risk == RiskLevel.HIGH:
            recommendations.append(
                "リスクが高まっています。一部ポジションの整理を検討してください。"
            )

        # ペグ関連
        if peg_status is not None:
            if peg_status.risk_level == RiskLevel.MEDIUM:
                recommendations.append(
                    "価格の連動性にやや乖離が見られます。状況を注視してください。"
                )
            elif peg_status.risk_level == RiskLevel.HIGH:
                recommendations.append(
                    "価格の連動性に乖離が広がっています。早めの対応を検討してください。"
                )
            elif peg_status.risk_level == RiskLevel.CRITICAL:
                recommendations.append("価格の連動性が大きく崩れています。早急な対応が必要です。")

        # 満期関連
        expiring_medium = [a for a in maturity_alerts if a.risk_level in (RiskLevel.MEDIUM,)]
        expiring_high = [
            a for a in maturity_alerts if a.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        ]
        if expiring_high:
            recommendations.append(
                "期限の迫った運用商品があります。早めに整理することを強くおすすめします。"
            )
        elif expiring_medium:
            recommendations.append(
                "一部の運用商品の期限が近づいています。計画的な整理をおすすめします。"
            )

        # プロトコル関連
        critical_protocols = [p for p in protocol_risks if p.risk_level == RiskLevel.CRITICAL]
        high_protocols = [p for p in protocol_risks if p.risk_level == RiskLevel.HIGH]
        if critical_protocols:
            recommendations.append(
                "一部の運用サービスで深刻な問題が検知されました。資産の安全を確認してください。"
            )
        elif high_protocols:
            recommendations.append(
                "一部の運用サービスでリスクが高まっています。状況を注視してください。"
            )

        # MEDIUM のとき固有メッセージがなければ追加
        if overall_risk == RiskLevel.MEDIUM and not recommendations:
            recommendations.append(
                "軽微なリスクが検知されています。定期的に状況を確認してください。"
            )

        return recommendations
