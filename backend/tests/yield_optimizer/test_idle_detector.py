# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/yield_optimizer/test_idle_detector.py
"""
IdleCapitalDetector のユニットテスト。

外部 Bybit / Privy API は全て MagicMock で差し替える。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from app.yield_optimizer.idle_detector import IDLE_THRESHOLD, IdleCapitalDetector
from app.yield_optimizer.schemas import YieldPosition

# ------------------------------------------------------------------ helpers


def _make_detector(
    bybit_free: str = "0",
    bybit_used: str = "0",
    morpho_positions: list[str] | None = None,
) -> IdleCapitalDetector:
    """
    テスト用 IdleCapitalDetector を生成する。

    Args:
        bybit_free: Bybit USDC free 残高
        bybit_used: Bybit USDC used 残高（ポジションあり判定）
        morpho_positions: Morpho 運用中 deposited_amount リスト (Decimal 文字列)
    """
    mock_exchange = MagicMock()
    mock_exchange.fetch_balance.return_value = {
        "USDC": {
            "free": float(bybit_free),
            "used": float(bybit_used),
            "total": float(Decimal(bybit_free) + Decimal(bybit_used)),
        }
    }

    mock_morpho = MagicMock()
    positions: list[YieldPosition] = []
    for deposited in morpho_positions or []:
        positions.append(
            YieldPosition(
                vault_address="0xtest",
                deposited_amount=deposited,
                current_value=deposited,
                earned_usd="0",
                last_updated=None,
            )
        )
    mock_morpho.get_all_positions.return_value = positions

    return IdleCapitalDetector(
        exchange_client=mock_exchange,
        morpho_client=mock_morpho,
        idle_threshold=IDLE_THRESHOLD,
    )


# ------------------------------------------------------------------ get_idle_capital


class TestGetIdleCapital:
    def test_idle_capital_is_bybit_minus_deployed(self) -> None:
        """アイドル = Bybit free - Morpho deployed。"""
        detector = _make_detector(
            bybit_free="500",
            morpho_positions=["200"],
        )
        idle = detector.get_idle_capital()
        assert idle == Decimal("300")

    def test_idle_capital_never_negative(self) -> None:
        """アイドルが負にならない (deployed > free の場合も 0)。"""
        detector = _make_detector(
            bybit_free="100",
            morpho_positions=["200"],
        )
        idle = detector.get_idle_capital()
        assert idle == Decimal("0")

    def test_idle_capital_no_morpho_positions(self) -> None:
        """Morpho ポジションなし → アイドル = Bybit free。"""
        detector = _make_detector(bybit_free="350")
        idle = detector.get_idle_capital()
        assert idle == Decimal("350")


# ------------------------------------------------------------------ should_deploy_to_morpho


class TestShouldDeployToMorpho:
    def test_should_deploy_true_when_idle_above_threshold_no_positions(self) -> None:
        """アイドル >= 閾値 かつ Bybit ポジションなし → True。"""
        detector = _make_detector(
            bybit_free="200",
            bybit_used="0",
        )
        assert detector.should_deploy_to_morpho() is True

    def test_should_deploy_false_when_bybit_has_open_positions(self) -> None:
        """Bybit にオープンポジションあり → False (デプロイしない)。"""
        detector = _make_detector(
            bybit_free="200",
            bybit_used="50",  # ポジションあり
        )
        assert detector.should_deploy_to_morpho() is False

    def test_should_deploy_false_when_idle_below_threshold(self) -> None:
        """アイドル < 閾値 ($100) → False。"""
        detector = _make_detector(
            bybit_free="99",
            bybit_used="0",
        )
        assert detector.should_deploy_to_morpho() is False

    def test_should_deploy_true_when_idle_exactly_at_threshold(self) -> None:
        """アイドル = 閾値 ちょうど → True (>= の境界値)。"""
        detector = _make_detector(
            bybit_free="100",
            bybit_used="0",
        )
        # idle = 100 >= IDLE_THRESHOLD(100) → True
        assert detector.should_deploy_to_morpho() is True

    def test_should_deploy_false_when_exchange_client_none(self) -> None:
        """exchange_client=None の場合は保守的に False (ポジションあり扱い)。"""
        detector = IdleCapitalDetector(
            exchange_client=None,
            morpho_client=None,
            idle_threshold=IDLE_THRESHOLD,
        )
        # exchange_client=None → get_bybit_free_usdc=0 → idle=0 < threshold=100 → False
        assert detector.should_deploy_to_morpho() is False


# ------------------------------------------------------------------ build_report


class TestBuildReport:
    def test_report_has_correct_fields(self) -> None:
        """build_report の出力フィールドを検証する。"""
        detector = _make_detector(
            bybit_free="500",
            bybit_used="0",
            morpho_positions=["100"],
        )
        report = detector.build_report()

        assert Decimal(report.bybit_free_usdc) == Decimal("500")
        assert Decimal(report.deployed_amount) == Decimal("100")
        assert Decimal(report.idle_amount) == Decimal("400")
        assert report.should_deploy is True
        assert report.reason is None
        assert report.checked_at  # ISO8601 文字列

    def test_report_has_reason_when_idle_below_threshold(self) -> None:
        """アイドル不足時はレポートに reason が含まれる。"""
        detector = _make_detector(bybit_free="50")
        report = detector.build_report()

        assert report.should_deploy is False
        assert report.reason is not None
        assert "閾値" in report.reason

    def test_report_reason_when_open_positions(self) -> None:
        """Bybit ポジションあり時はレポートに reason が含まれる。"""
        detector = _make_detector(bybit_free="300", bybit_used="100")
        report = detector.build_report()

        assert report.should_deploy is False
        assert report.reason is not None
        assert "ポジション" in report.reason


# ------------------------------------------------------------------ fail-open


class TestFailOpen:
    def test_get_bybit_free_usdc_fail_open(self) -> None:
        """Bybit API 失敗時は 0 を返す (fail-open)。"""
        mock_exchange = MagicMock()
        mock_exchange.fetch_balance.side_effect = ConnectionError("Network error")

        detector = IdleCapitalDetector(
            exchange_client=mock_exchange,
            idle_threshold=IDLE_THRESHOLD,
        )
        result = detector.get_bybit_free_usdc()
        assert result == Decimal("0")

    def test_get_deployed_amount_fail_open(self) -> None:
        """Morpho API 失敗時は 0 を返す (fail-open)。"""
        mock_morpho = MagicMock()
        mock_morpho.get_all_positions.side_effect = Exception("API timeout")

        detector = IdleCapitalDetector(
            exchange_client=None,
            morpho_client=mock_morpho,
            idle_threshold=IDLE_THRESHOLD,
        )
        result = detector.get_deployed_amount()
        assert result == Decimal("0")
