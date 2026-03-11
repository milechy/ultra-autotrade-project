"""
Comprehensive unit tests for scripts/backtest_weekly.py.

All tests are deterministic (seeded RNG or hand-crafted fixtures).
No real network calls are made (requests is fully mocked).
"""

import math
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import backtest_weekly as bw
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade(pnl: float, portfolio_value: float, return_val: float = 0.0) -> dict:
    """Build a minimal trade dict compatible with the module's expectations."""
    return {
        "date": "2025-01-01",
        "return": return_val,
        "pnl_usdt": pnl,
        "portfolio_value": portfolio_value,
        "is_win": pnl >= 0,
    }


def _make_hf_day(hf: float, violation: bool | None = None) -> dict:
    """Build a minimal HF-series entry."""
    if violation is None:
        violation = hf < float(bw.HF_THRESHOLD)
    return {"date": "2025-01-01", "health_factor": hf, "violation": violation}


# ===========================================================================
# generate_trades
# ===========================================================================


class TestGenerateTrades:
    def test_returns_list(self):
        trades = bw.generate_trades(seed=42)
        assert isinstance(trades, list)

    def test_non_empty(self):
        trades = bw.generate_trades(seed=42)
        assert len(trades) > 0

    def test_trade_count_in_range(self):
        """generate_trades must produce between 50 and 100 trades."""
        trades = bw.generate_trades(seed=42)
        assert 50 <= len(trades) <= 100

    def test_deterministic_same_seed(self):
        """Same seed → identical output."""
        a = bw.generate_trades(seed=7)
        b = bw.generate_trades(seed=7)
        assert a == b

    def test_different_seeds_differ(self):
        """Different seeds → different outputs."""
        a = bw.generate_trades(seed=1)
        b = bw.generate_trades(seed=2)
        assert a != b

    def test_trade_keys(self):
        trades = bw.generate_trades(seed=42)
        required_keys = {"date", "return", "pnl_usdt", "portfolio_value", "is_win"}
        for trade in trades:
            assert required_keys.issubset(trade.keys())

    def test_is_win_consistent_with_pnl(self):
        trades = bw.generate_trades(seed=42)
        for trade in trades:
            if trade["pnl_usdt"] >= 0:
                assert trade["is_win"] is True
            else:
                assert trade["is_win"] is False

    def test_portfolio_value_positive(self):
        trades = bw.generate_trades(seed=42)
        for trade in trades:
            assert trade["portfolio_value"] > 0


# ===========================================================================
# generate_hf_series
# ===========================================================================


class TestGenerateHfSeries:
    def test_length_equals_simulation_days(self):
        series = bw.generate_hf_series(seed=42)
        assert len(series) == bw.SIMULATION_DAYS

    def test_deterministic_same_seed(self):
        a = bw.generate_hf_series(seed=99)
        b = bw.generate_hf_series(seed=99)
        assert a == b

    def test_hf_floor_respected(self):
        """Health factor must never fall below 0.5 (floor in implementation)."""
        series = bw.generate_hf_series(seed=42)
        for day in series:
            assert day["health_factor"] >= 0.5

    def test_violation_flag_consistent(self):
        """violation field must be True iff health_factor < 1.6."""
        series = bw.generate_hf_series(seed=42)
        for day in series:
            expected = day["health_factor"] < float(bw.HF_THRESHOLD)
            assert day["violation"] == expected

    def test_hf_series_keys(self):
        series = bw.generate_hf_series(seed=42)
        required_keys = {"date", "health_factor", "violation"}
        for day in series:
            assert required_keys.issubset(day.keys())


# ===========================================================================
# calculate_win_rate
# ===========================================================================


class TestCalculateWinRate:
    def test_empty_returns_zero(self):
        assert bw.calculate_win_rate([]) == Decimal("0")

    def test_all_wins(self):
        trades = [_make_trade(100, 10100), _make_trade(50, 10150)]
        assert bw.calculate_win_rate(trades) == Decimal("1.0000")

    def test_all_losses(self):
        trades = [_make_trade(-100, 9900), _make_trade(-50, 9850)]
        assert bw.calculate_win_rate(trades) == Decimal("0.0000")

    def test_half_wins(self):
        trades = [_make_trade(100, 10100), _make_trade(-50, 10050)]
        result = bw.calculate_win_rate(trades)
        assert result == Decimal("0.5000")

    def test_returns_decimal(self):
        trades = [_make_trade(10, 10010)]
        assert isinstance(bw.calculate_win_rate(trades), Decimal)

    def test_quantized_to_4_decimal_places(self):
        """Win rate must be quantized to 4 decimal places."""
        trades = [_make_trade(1, 10001)] * 3 + [_make_trade(-1, 9999)] * 2
        result = bw.calculate_win_rate(trades)
        # 3/5 = 0.6000
        assert result == Decimal("0.6000")

    def test_three_out_of_four(self):
        trades = [_make_trade(1, 1)] * 3 + [_make_trade(-1, 0)]
        result = bw.calculate_win_rate(trades)
        assert result == Decimal("0.7500")


# ===========================================================================
# calculate_max_drawdown
# ===========================================================================


class TestCalculateMaxDrawdown:
    def test_empty_returns_zero(self):
        assert bw.calculate_max_drawdown([]) == Decimal("0")

    def test_returns_decimal(self):
        trades = [_make_trade(10, 10010)]
        assert isinstance(bw.calculate_max_drawdown(trades), Decimal)

    def test_no_drawdown_monotone_increase(self):
        """Portfolio that only goes up should have zero drawdown."""
        trades = [
            _make_trade(100, 10100),
            _make_trade(100, 10200),
            _make_trade(100, 10300),
        ]
        result = bw.calculate_max_drawdown(trades)
        assert result == Decimal("0.0000")

    def test_known_drawdown(self):
        """
        Initial = 10000, rises to 12000, drops to 9000.
        Max drawdown = (12000 - 9000) / 12000 = 0.25 → 0.2500.
        """
        trades = [
            _make_trade(2000, 12000),
            _make_trade(-3000, 9000),
        ]
        result = bw.calculate_max_drawdown(trades)
        assert result == Decimal("0.2500")

    def test_drawdown_from_initial_value(self):
        """
        The initial portfolio value (10000) is prepended, so a drop on the
        very first trade is captured.
        Drop from 10000 → 8000 = 20 % drawdown.
        """
        trades = [_make_trade(-2000, 8000)]
        result = bw.calculate_max_drawdown(trades)
        assert result == Decimal("0.2000")

    def test_quantized_to_4_decimal_places(self):
        trades = [_make_trade(-2000, 8000)]
        result = bw.calculate_max_drawdown(trades)
        # Ensure it has exactly 4 decimal places
        assert result == result.quantize(Decimal("0.0001"))


# ===========================================================================
# calculate_sharpe_ratio
# ===========================================================================


class TestCalculateSharpeRatio:
    def test_empty_returns_zero(self):
        assert bw.calculate_sharpe_ratio([]) == Decimal("0")

    def test_single_trade_returns_zero(self):
        assert bw.calculate_sharpe_ratio([_make_trade(1, 1, 0.01)]) == Decimal("0")

    def test_returns_decimal(self):
        trades = [_make_trade(1, 1, 0.01), _make_trade(1, 1, 0.02)]
        assert isinstance(bw.calculate_sharpe_ratio(trades), Decimal)

    def test_zero_std_returns_zero(self):
        """Identical returns → std dev = 0 → Sharpe = 0."""
        trades = [_make_trade(1, 1, return_val=0.01) for _ in range(5)]
        result = bw.calculate_sharpe_ratio(trades)
        assert result == Decimal("0")

    def test_known_sharpe_value(self):
        """
        Hand-compute a simple Sharpe:
        returns = [0.04, 0.02]
        mean = 0.03, std (sample, n-1) = sqrt(((0.04-0.03)^2+(0.02-0.03)^2)/1) = 0.01*sqrt(2)
        excess = 0.03 - RISK_FREE_RATE_DAILY
        sharpe = excess / (0.01*sqrt(2)) * sqrt(252)
        """
        rfr = bw.RISK_FREE_RATE_DAILY
        returns = [0.04, 0.02]
        mean_r = sum(returns) / len(returns)  # 0.03
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1))
        expected_sharpe = round(((mean_r - rfr) / std_r) * math.sqrt(252), 4)

        trades = [
            _make_trade(1, 1, return_val=returns[0]),
            _make_trade(1, 1, return_val=returns[1]),
        ]
        result = bw.calculate_sharpe_ratio(trades)
        assert float(result) == pytest.approx(expected_sharpe, abs=1e-3)

    def test_negative_sharpe_possible(self):
        """Strongly negative returns → Sharpe can be negative."""
        trades = [_make_trade(-1, 1, return_val=-0.05 + i * 0.001) for i in range(10)]
        result = bw.calculate_sharpe_ratio(trades)
        assert isinstance(result, Decimal)
        # Result must be a valid number (not NaN / exception)
        assert not math.isnan(float(result))


# ===========================================================================
# count_hf_violations
# ===========================================================================


class TestCountHfViolations:
    def test_empty_series(self):
        assert bw.count_hf_violations([]) == 0

    def test_no_violations(self):
        series = [_make_hf_day(2.0), _make_hf_day(1.8), _make_hf_day(1.7)]
        assert bw.count_hf_violations(series) == 0

    def test_all_violations(self):
        series = [_make_hf_day(1.2), _make_hf_day(1.4), _make_hf_day(1.5)]
        assert bw.count_hf_violations(series) == 3

    def test_mixed(self):
        series = [
            _make_hf_day(2.0),  # OK
            _make_hf_day(1.3),  # violation
            _make_hf_day(1.7),  # OK
            _make_hf_day(1.1),  # violation
        ]
        assert bw.count_hf_violations(series) == 2

    def test_boundary_exactly_1_6_is_not_violation(self):
        """HF exactly at threshold (1.6) must NOT be counted as a violation."""
        series = [_make_hf_day(1.6, violation=False)]
        assert bw.count_hf_violations(series) == 0

    def test_returns_int(self):
        assert isinstance(bw.count_hf_violations([_make_hf_day(1.0)]), int)


# ===========================================================================
# _status_emoji_and_color
# ===========================================================================


class TestStatusEmojiAndColor:
    def test_pass_good_metrics(self):
        status, color, assessment = bw._status_emoji_and_color(
            sharpe=Decimal("1.5"),
            max_drawdown=Decimal("0.10"),
            hf_violations=0,
        )
        assert status == "PASS"
        assert color == "green"
        assert "acceptable" in assessment.lower()

    def test_warn_borderline_sharpe(self):
        status, color, _ = bw._status_emoji_and_color(
            sharpe=Decimal("0.7"),
            max_drawdown=Decimal("0.10"),
            hf_violations=0,
        )
        assert status == "WARN"
        assert color == "yellow"

    def test_warn_borderline_drawdown(self):
        status, color, _ = bw._status_emoji_and_color(
            sharpe=Decimal("1.5"),
            max_drawdown=Decimal("0.25"),
            hf_violations=0,
        )
        assert status == "WARN"
        assert color == "yellow"

    def test_warn_few_hf_violations(self):
        status, color, _ = bw._status_emoji_and_color(
            sharpe=Decimal("1.5"),
            max_drawdown=Decimal("0.10"),
            hf_violations=2,
        )
        assert status == "WARN"
        assert color == "yellow"

    def test_fail_bad_metrics(self):
        status, color, assessment = bw._status_emoji_and_color(
            sharpe=Decimal("0.2"),
            max_drawdown=Decimal("0.45"),
            hf_violations=10,
        )
        assert status == "FAIL"
        assert color == "red"
        assert "exceed" in assessment.lower() or "risk" in assessment.lower()

    def test_fail_many_hf_violations_only(self):
        """Many HF violations alone should cause FAIL (not borderline)."""
        status, _, _ = bw._status_emoji_and_color(
            sharpe=Decimal("1.5"),
            max_drawdown=Decimal("0.10"),
            hf_violations=10,
        )
        assert status == "FAIL"

    def test_returns_three_tuple(self):
        result = bw._status_emoji_and_color(
            sharpe=Decimal("1.5"),
            max_drawdown=Decimal("0.10"),
            hf_violations=0,
        )
        assert len(result) == 3


# ===========================================================================
# build_slack_payload
# ===========================================================================


class TestBuildSlackPayload:
    _BASE_ARGS = {
        "date_start": "2025-01-01",
        "date_end": "2025-04-01",
        "win_rate": Decimal("0.6000"),
        "sharpe": Decimal("1.5000"),
        "max_drawdown": Decimal("0.1000"),
        "hf_violations": 0,
        "n_trades": 75,
        "final_portfolio": Decimal("11000"),
    }

    def test_returns_dict(self):
        payload = bw.build_slack_payload(**self._BASE_ARGS)
        assert isinstance(payload, dict)

    def test_text_key_present(self):
        payload = bw.build_slack_payload(**self._BASE_ARGS)
        assert "text" in payload

    def test_blocks_key_present(self):
        payload = bw.build_slack_payload(**self._BASE_ARGS)
        assert "blocks" in payload
        assert isinstance(payload["blocks"], list)

    def test_status_label_in_text(self):
        payload = bw.build_slack_payload(**self._BASE_ARGS)
        assert "PASS" in payload["text"]

    def test_date_range_in_text(self):
        payload = bw.build_slack_payload(**self._BASE_ARGS)
        assert "2025-01-01" in payload["text"]
        assert "2025-04-01" in payload["text"]

    def test_positive_pnl_has_plus_sign(self):
        """1000 USDT gain over initial 10000 → P&L field contains '+'."""
        payload = bw.build_slack_payload(**self._BASE_ARGS)
        blocks_text = str(payload["blocks"])
        assert "+1000" in blocks_text or "+10.00" in blocks_text

    def test_negative_pnl_no_plus_sign_in_pnl_field(self):
        """Portfolio below initial → no '+' prefix on the pnl value."""
        args = {**self._BASE_ARGS, "final_portfolio": Decimal("9000")}
        payload = bw.build_slack_payload(**args)
        blocks_text = str(payload["blocks"])
        # Negative pnl should appear as a plain negative number
        assert "-1000" in blocks_text or "-10.00" in blocks_text

    def test_header_block_contains_dates(self):
        payload = bw.build_slack_payload(**self._BASE_ARGS)
        header = payload["blocks"][0]
        assert header["type"] == "header"
        assert "2025-01-01" in header["text"]["text"]

    def test_warn_status_reflected(self):
        args = {**self._BASE_ARGS, "sharpe": Decimal("0.7")}
        payload = bw.build_slack_payload(**args)
        assert "WARN" in payload["text"]

    def test_fail_status_reflected(self):
        args = {
            **self._BASE_ARGS,
            "sharpe": Decimal("0.2"),
            "max_drawdown": Decimal("0.45"),
            "hf_violations": 10,
        }
        payload = bw.build_slack_payload(**args)
        assert "FAIL" in payload["text"]


# ===========================================================================
# build_results_dict
# ===========================================================================


class TestBuildResultsDict:
    _BASE_ARGS = {
        "date_start": "2025-01-01",
        "date_end": "2025-04-01",
        "win_rate": Decimal("0.6000"),
        "sharpe": Decimal("1.5000"),
        "max_drawdown": Decimal("0.1000"),
        "hf_violations": 0,
        "n_trades": 75,
        "final_portfolio": Decimal("11000"),
    }

    def test_returns_dict(self):
        result = bw.build_results_dict(**self._BASE_ARGS)
        assert isinstance(result, dict)

    def test_required_top_level_keys(self):
        result = bw.build_results_dict(**self._BASE_ARGS)
        for key in ("generated_at", "period", "metrics", "thresholds", "status", "assessment"):
            assert key in result, f"Missing key: {key}"

    def test_period_values(self):
        result = bw.build_results_dict(**self._BASE_ARGS)
        assert result["period"]["start"] == "2025-01-01"
        assert result["period"]["end"] == "2025-04-01"
        assert result["period"]["days"] == bw.SIMULATION_DAYS

    def test_metrics_values(self):
        result = bw.build_results_dict(**self._BASE_ARGS)
        metrics = result["metrics"]
        assert metrics["win_rate"] == pytest.approx(0.6)
        assert metrics["sharpe_ratio"] == pytest.approx(1.5)
        assert metrics["max_drawdown"] == pytest.approx(0.1)
        assert metrics["hf_violations"] == 0
        assert metrics["n_trades"] == 75
        assert metrics["final_portfolio_usdt"] == pytest.approx(11000.0)

    def test_status_pass(self):
        result = bw.build_results_dict(**self._BASE_ARGS)
        assert result["status"] == "PASS"

    def test_thresholds_structure(self):
        result = bw.build_results_dict(**self._BASE_ARGS)
        thresholds = result["thresholds"]
        assert thresholds["sharpe_min"] == 1.0
        assert thresholds["max_drawdown_limit"] == 0.20
        assert thresholds["hf_violations_limit"] == 0

    def test_generated_at_is_iso_string(self):
        result = bw.build_results_dict(**self._BASE_ARGS)
        # Should be parseable as an ISO datetime string
        from datetime import datetime

        dt = datetime.fromisoformat(result["generated_at"])
        assert dt is not None


# ===========================================================================
# send_slack_notification
# ===========================================================================


class TestSendSlackNotification:
    _DUMMY_PAYLOAD = {"text": "test", "blocks": []}

    def test_returns_false_without_env_var(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove SLACK_WEBHOOK_URL if set
            os.environ.pop("SLACK_WEBHOOK_URL", None)
            result = bw.send_slack_notification(self._DUMMY_PAYLOAD)
        assert result is False

    def test_returns_true_on_success(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)

        with (
            patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/fake"}),
            patch("backtest_weekly.requests.post", return_value=mock_response) as mock_post,
        ):
            result = bw.send_slack_notification(self._DUMMY_PAYLOAD)

        assert result is True
        mock_post.assert_called_once()

    def test_returns_false_on_request_exception(self):
        import requests as req

        with (
            patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/fake"}),
            patch(
                "backtest_weekly.requests.post",
                side_effect=req.exceptions.RequestException("timeout"),
            ),
        ):
            result = bw.send_slack_notification(self._DUMMY_PAYLOAD)

        assert result is False

    def test_posts_to_correct_url(self):
        url = "https://hooks.slack.com/services/TEST/TEST/TOKEN"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)

        with (
            patch.dict(os.environ, {"SLACK_WEBHOOK_URL": url}),
            patch("backtest_weekly.requests.post", return_value=mock_response) as mock_post,
        ):
            bw.send_slack_notification(self._DUMMY_PAYLOAD)

        args, kwargs = mock_post.call_args
        assert args[0] == url

    def test_payload_sent_as_json(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)

        with (
            patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/fake"}),
            patch("backtest_weekly.requests.post", return_value=mock_response) as mock_post,
        ):
            bw.send_slack_notification(self._DUMMY_PAYLOAD)

        _, kwargs = mock_post.call_args
        assert kwargs.get("json") == self._DUMMY_PAYLOAD

    def test_timeout_is_set(self):
        """Requests should be made with a timeout to avoid hanging."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)

        with (
            patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/fake"}),
            patch("backtest_weekly.requests.post", return_value=mock_response) as mock_post,
        ):
            bw.send_slack_notification(self._DUMMY_PAYLOAD)

        _, kwargs = mock_post.call_args
        assert kwargs.get("timeout") is not None


# ===========================================================================
# Integration-style: full pipeline with seeded data
# ===========================================================================


class TestFullPipeline:
    def test_pipeline_produces_valid_metrics(self):
        """End-to-end: seeded data → all metrics are valid Decimals / ints."""
        trades = bw.generate_trades(seed=42)
        hf_series = bw.generate_hf_series(seed=42)

        win_rate = bw.calculate_win_rate(trades)
        max_dd = bw.calculate_max_drawdown(trades)
        sharpe = bw.calculate_sharpe_ratio(trades)
        violations = bw.count_hf_violations(hf_series)

        assert isinstance(win_rate, Decimal)
        assert isinstance(max_dd, Decimal)
        assert isinstance(sharpe, Decimal)
        assert isinstance(violations, int)

        assert Decimal("0") <= win_rate <= Decimal("1")
        assert max_dd >= Decimal("0")
        assert violations >= 0

    def test_pipeline_produces_valid_slack_payload(self):
        trades = bw.generate_trades(seed=42)
        hf_series = bw.generate_hf_series(seed=42)

        win_rate = bw.calculate_win_rate(trades)
        max_dd = bw.calculate_max_drawdown(trades)
        sharpe = bw.calculate_sharpe_ratio(trades)
        violations = bw.count_hf_violations(hf_series)
        final_portfolio = Decimal(str(trades[-1]["portfolio_value"]))

        payload = bw.build_slack_payload(
            date_start="2025-01-01",
            date_end="2025-04-01",
            win_rate=win_rate,
            sharpe=sharpe,
            max_drawdown=max_dd,
            hf_violations=violations,
            n_trades=len(trades),
            final_portfolio=final_portfolio,
        )

        assert "text" in payload
        assert "blocks" in payload
        assert len(payload["blocks"]) > 0
