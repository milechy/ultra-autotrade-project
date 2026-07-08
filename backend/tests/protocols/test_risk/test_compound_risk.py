"""CompoundRiskAssessor のユニットテスト。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.protocols.risk.compound_risk import CompoundRiskAssessor
from app.protocols.risk.schemas import (
    CompoundRiskAssessment,
    MaturityAlert,
    PegStatus,
    ProtocolHealth,
    RiskLevel,
)

# 英語ジャーゴンリスト（推奨文に含まれてはいけない語）
_FORBIDDEN_JARGON = ["APY", "yield", "protocol", "peg", "maturity", "TVL", "HF"]


def _make_protocol_health(
    risk_level: RiskLevel, *, is_operational: bool = True, protocol: str = "test"
) -> ProtocolHealth:
    from datetime import datetime, timezone

    return ProtocolHealth(
        protocol=protocol,
        risk_level=risk_level,
        tvl_usd=Decimal("1000000"),
        tvl_change_24h_pct=Decimal("0"),
        is_operational=is_operational,
        last_checked=datetime.now(tz=timezone.utc),
        alerts=[],
    )


def _make_peg_status(risk_level: RiskLevel) -> PegStatus:
    from datetime import datetime, timezone

    return PegStatus(
        current_ratio=Decimal("1.0"),
        deviation_pct=Decimal("0"),
        risk_level=risk_level,
        last_checked=datetime.now(tz=timezone.utc),
    )


def _make_maturity_alert(risk_level: RiskLevel) -> MaturityAlert:
    from datetime import datetime, timezone

    return MaturityAlert(
        market_address="0x" + "0" * 40,
        asset="stETH",
        maturity_date=datetime.now(tz=timezone.utc),
        days_remaining=10,
        risk_level=risk_level,
        action_required="monitor",
    )


class TestAssess:
    @pytest.mark.asyncio
    async def test_assess_returns_compound_risk_assessment(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert isinstance(result, CompoundRiskAssessment)

    @pytest.mark.asyncio
    async def test_assess_protocol_risks_has_three_entries(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert len(result.protocol_risks) == 3

    @pytest.mark.asyncio
    async def test_assess_peg_status_is_included(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert result.peg_status is not None
        assert isinstance(result.peg_status, PegStatus)

    @pytest.mark.asyncio
    async def test_assess_maturity_alerts_is_included(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert result.maturity_alerts is not None

    @pytest.mark.asyncio
    async def test_assess_risk_score_is_decimal(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert isinstance(result.risk_score, Decimal)

    @pytest.mark.asyncio
    async def test_assess_total_exposure_is_decimal(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert isinstance(result.total_exposure_usd, Decimal)

    @pytest.mark.asyncio
    async def test_assess_normal_state_no_evacuation(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert result.should_evacuate is False

    @pytest.mark.asyncio
    async def test_assess_critical_peg_triggers_evacuation(
        self, mock_lido_client: AsyncMock, protocol_monitor: object, maturity_manager: object
    ) -> None:
        """CRITICAL ペグ乖離のとき should_evacuate=True を返す。"""
        mock_lido_client.get_steth_eth_ratio.return_value = Decimal("0.97")  # 3% 乖離
        from app.protocols.risk.peg_monitor import PegMonitor

        peg_mon = PegMonitor(lido_client=mock_lido_client)
        assessor = CompoundRiskAssessor(
            protocol_monitor=protocol_monitor,  # type: ignore[arg-type]
            peg_monitor=peg_mon,
            maturity_manager=maturity_manager,  # type: ignore[arg-type]
        )
        result = await assessor.assess()
        assert result.should_evacuate is True

    @pytest.mark.asyncio
    async def test_assess_recommendations_non_empty(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_assess_recommendations_no_jargon(
        self, compound_assessor: CompoundRiskAssessor
    ) -> None:
        result = await compound_assessor.assess()
        for rec in result.recommendations:
            for jargon in _FORBIDDEN_JARGON:
                assert jargon not in rec, (
                    f"推奨文に英語ジャーゴン '{jargon}' が含まれています: {rec}"
                )


class TestEvacuationOperationalGuard:
    """probe 失敗 (is_operational=False) のプロトコルを避難根拠から除外する二重防御。

    2026-06-28 Lido 誤検知の再発防止。protocol_monitor が probe 失敗を LOW にするのが
    一次防御だが、万一 CRITICAL + 監視不能が来ても避難アラートを出さないことを保証する。
    """

    def _build_assessor(self, protocol_risks: list[ProtocolHealth]) -> CompoundRiskAssessor:
        """protocol_risks を返す mock を注入した assessor を組み立てる。

        peg / maturity は避難条件に触れない (LOW / 空) 状態にして、プロトコル判定のみを検証する。
        """
        protocol_monitor = AsyncMock()
        protocol_monitor.check_all.return_value = protocol_risks
        peg_monitor = AsyncMock()
        peg_monitor.get_peg_status.return_value = _make_peg_status(RiskLevel.LOW)
        maturity_manager = AsyncMock()
        maturity_manager.check_maturities.return_value = []
        return CompoundRiskAssessor(
            protocol_monitor=protocol_monitor,
            peg_monitor=peg_monitor,
            maturity_manager=maturity_manager,
        )

    @pytest.mark.asyncio
    async def test_critical_but_not_operational_does_not_evacuate(self) -> None:
        """CRITICAL でも is_operational=False (監視不能) なら should_evacuate=False。"""
        assessor = self._build_assessor(
            [
                _make_protocol_health(RiskLevel.CRITICAL, is_operational=False, protocol="lido"),
                _make_protocol_health(RiskLevel.LOW, protocol="aave"),
                _make_protocol_health(RiskLevel.LOW, protocol="pendle"),
            ]
        )
        result = await assessor.assess()
        assert result.should_evacuate is False
        assert result.evacuation_reason is None

    @pytest.mark.asyncio
    async def test_critical_and_operational_still_evacuates(self) -> None:
        """CRITICAL かつ is_operational=True なら従来通り should_evacuate=True（退行防止）。"""
        assessor = self._build_assessor(
            [
                _make_protocol_health(RiskLevel.CRITICAL, is_operational=True, protocol="lido"),
                _make_protocol_health(RiskLevel.LOW, protocol="aave"),
                _make_protocol_health(RiskLevel.LOW, protocol="pendle"),
            ]
        )
        result = await assessor.assess()
        assert result.should_evacuate is True
        assert result.evacuation_reason is not None
        assert "lido" in result.evacuation_reason

    @pytest.mark.asyncio
    async def test_operational_critical_only_names_operational_protocol(self) -> None:
        """避難理由には is_operational=True の CRITICAL プロトコルのみ列挙する。"""
        assessor = self._build_assessor(
            [
                _make_protocol_health(RiskLevel.CRITICAL, is_operational=False, protocol="lido"),
                _make_protocol_health(RiskLevel.CRITICAL, is_operational=True, protocol="aave"),
                _make_protocol_health(RiskLevel.LOW, protocol="pendle"),
            ]
        )
        result = await assessor.assess()
        assert result.should_evacuate is True
        assert result.evacuation_reason is not None
        assert "aave" in result.evacuation_reason
        assert "lido" not in result.evacuation_reason


class TestCalculateRiskScore:
    def test_score_0_to_20_is_low(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        all_low = [
            _make_protocol_health(RiskLevel.LOW),
            _make_protocol_health(RiskLevel.LOW),
            _make_protocol_health(RiskLevel.LOW),
        ]
        peg = _make_peg_status(RiskLevel.LOW)
        maturities: list[MaturityAlert] = []
        score = assessor.calculate_risk_score(all_low, peg, maturities)
        assert score <= Decimal("20")

    def test_score_medium_protocol_returns_higher_score(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        risks = [
            _make_protocol_health(RiskLevel.MEDIUM),
            _make_protocol_health(RiskLevel.LOW),
            _make_protocol_health(RiskLevel.LOW),
        ]
        peg = _make_peg_status(RiskLevel.LOW)
        maturities: list[MaturityAlert] = []
        score = assessor.calculate_risk_score(risks, peg, maturities)
        assert score > Decimal("0")

    def test_score_any_critical_clamps_to_80_minimum(self) -> None:
        """CRITICAL コンポーネントがある場合スコアは最低 80。"""
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        risks = [
            _make_protocol_health(RiskLevel.CRITICAL),
            _make_protocol_health(RiskLevel.LOW),
            _make_protocol_health(RiskLevel.LOW),
        ]
        peg = _make_peg_status(RiskLevel.LOW)
        maturities: list[MaturityAlert] = []
        score = assessor.calculate_risk_score(risks, peg, maturities)
        assert score >= Decimal("80")

    def test_score_non_operational_critical_does_not_clamp_to_80(self) -> None:
        """is_operational=False の CRITICAL プロトコルは 80 クランプに算入しない。

        監視不能プロトコル (probe 失敗) を危険域スコアに数えない二重防御
        （2026-06-28 Lido 誤検知対策）。他コンポーネントが LOW なら 80 未満に留まる。
        """
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        risks = [
            _make_protocol_health(RiskLevel.CRITICAL, is_operational=False),
            _make_protocol_health(RiskLevel.LOW),
            _make_protocol_health(RiskLevel.LOW),
        ]
        peg = _make_peg_status(RiskLevel.LOW)
        maturities: list[MaturityAlert] = []
        score = assessor.calculate_risk_score(risks, peg, maturities)
        assert score < Decimal("80")

    def test_score_critical_peg_clamps_to_80(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        risks = [_make_protocol_health(RiskLevel.LOW)] * 3
        peg = _make_peg_status(RiskLevel.CRITICAL)
        maturities: list[MaturityAlert] = []
        score = assessor.calculate_risk_score(risks, peg, maturities)
        assert score >= Decimal("80")

    def test_score_is_decimal_type(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        risks = [_make_protocol_health(RiskLevel.LOW)] * 3
        peg = _make_peg_status(RiskLevel.LOW)
        score = assessor.calculate_risk_score(risks, peg, [])
        assert isinstance(score, Decimal)

    def test_score_capped_at_100(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        risks = [_make_protocol_health(RiskLevel.CRITICAL)] * 3
        peg = _make_peg_status(RiskLevel.CRITICAL)
        maturities = [_make_maturity_alert(RiskLevel.CRITICAL)]
        score = assessor.calculate_risk_score(risks, peg, maturities)
        assert score <= Decimal("100")


class TestDetermineOverallRisk:
    def test_score_0_is_low(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("0")) == RiskLevel.LOW

    def test_score_20_is_low(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("20")) == RiskLevel.LOW

    def test_score_21_is_medium(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("21")) == RiskLevel.MEDIUM

    def test_score_40_is_medium(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("40")) == RiskLevel.MEDIUM

    def test_score_41_is_high(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("41")) == RiskLevel.HIGH

    def test_score_70_is_high(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("70")) == RiskLevel.HIGH

    def test_score_71_is_critical(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("71")) == RiskLevel.CRITICAL

    def test_score_100_is_critical(self) -> None:
        assessor = CompoundRiskAssessor.__new__(CompoundRiskAssessor)
        assert assessor._determine_overall_risk(Decimal("100")) == RiskLevel.CRITICAL
