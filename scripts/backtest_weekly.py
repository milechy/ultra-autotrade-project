#!/usr/bin/env python3
"""
Weekly backtest script for Ultra AutoTrade.

Generates 90 days of simulated trading data, calculates key metrics,
and sends a report to Slack.

Usage:
    python scripts/backtest_weekly.py

Environment:
    SLACK_WEBHOOK_URL  Slack incoming webhook URL (required)

Exit codes:
    0  Success (report sent)
    1  Failure (calculation error or Slack delivery failure)
"""

import json
import math
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests package not installed. Run: pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SIMULATION_DAYS = 90
INITIAL_PORTFOLIO_USDT = Decimal("10000")
TRADE_MEAN_RETURN = 0.002  # slight positive drift per trade
TRADE_STD_RETURN = 0.03  # realistic crypto volatility
RISK_FREE_RATE_DAILY = 0.02 / 252  # annualised 2% → daily

HF_INITIAL = Decimal("2.0")
HF_THRESHOLD = Decimal("1.6")
HF_DRIFT = 0.0  # no systematic drift
HF_VOLATILITY = 0.08  # random walk step size


# ---------------------------------------------------------------------------
# Mock data generation
# ---------------------------------------------------------------------------


def generate_trades(seed: int = 42) -> list[dict[str, Any]]:
    """Generate simulated trades over SIMULATION_DAYS days."""
    rng = random.Random(seed)  # noqa: S311
    trades: list[dict[str, Any]] = []

    start_date = datetime.now(tz=UTC).date() - timedelta(days=SIMULATION_DAYS)
    portfolio_value = INITIAL_PORTFOLIO_USDT

    # Produce 50–100 trades spread across the window
    n_trades = rng.randint(50, 100)
    # Pick n_trades random days (with possible duplicates = multiple trades/day)
    trade_days_offsets = sorted(rng.randint(0, SIMULATION_DAYS - 1) for _ in range(n_trades))

    for offset in trade_days_offsets:
        trade_date = start_date + timedelta(days=offset)
        raw_return = rng.gauss(TRADE_MEAN_RETURN, TRADE_STD_RETURN)
        # Use Decimal for financial calculation (per security rules)
        return_decimal = Decimal(str(round(raw_return, 8)))
        pnl = (portfolio_value * return_decimal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        portfolio_value = (portfolio_value + pnl).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        trades.append(
            {
                "date": trade_date.isoformat(),
                "return": float(return_decimal),
                "pnl_usdt": float(pnl),
                "portfolio_value": float(portfolio_value),
                "is_win": pnl >= Decimal("0"),
            }
        )

    return trades


def generate_hf_series(seed: int = 42) -> list[dict[str, Any]]:
    """
    Simulate Aave Health Factor as a random walk over SIMULATION_DAYS days.

    Occasionally dips below 1.6 to test violation detection.
    """
    rng = random.Random(seed + 1)  # noqa: S311
    series: list[dict[str, Any]] = []

    start_date = datetime.now(tz=UTC).date() - timedelta(days=SIMULATION_DAYS)
    hf = float(HF_INITIAL)

    for day in range(SIMULATION_DAYS):
        current_date = start_date + timedelta(days=day)
        # Random walk with slight mean-reversion toward 2.0
        mean_reversion = 0.02 * (float(HF_INITIAL) - hf)
        step = rng.gauss(mean_reversion + HF_DRIFT, HF_VOLATILITY)
        hf = max(0.5, hf + step)  # floor at 0.5 to avoid negative
        series.append(
            {
                "date": current_date.isoformat(),
                "health_factor": round(hf, 4),
                "violation": hf < float(HF_THRESHOLD),
            }
        )

    return series


# ---------------------------------------------------------------------------
# Metric calculations (Decimal for financial figures)
# ---------------------------------------------------------------------------


def calculate_win_rate(trades: list[dict[str, Any]]) -> Decimal:
    if not trades:
        return Decimal("0")
    wins = sum(1 for t in trades if t["is_win"])
    ratio = Decimal(wins) / Decimal(len(trades))
    return ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calculate_max_drawdown(trades: list[dict[str, Any]]) -> Decimal:
    """Max Drawdown = (peak − trough) / peak over portfolio value series."""
    if not trades:
        return Decimal("0")

    values = [Decimal(str(t["portfolio_value"])) for t in trades]
    # Prepend initial value so drawdown from start is captured
    values = [INITIAL_PORTFOLIO_USDT] + values

    peak = values[0]
    max_dd = Decimal("0")
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > Decimal("0") else Decimal("0")
        if dd > max_dd:
            max_dd = dd

    return max_dd.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calculate_sharpe_ratio(trades: list[dict[str, Any]]) -> Decimal:
    """
    Sharpe Ratio = (mean_return - risk_free_rate) / std_return * sqrt(252).

    Uses annualised scaling (252 trading days).
    """
    if len(trades) < 2:
        return Decimal("0")

    returns = [t["return"] for t in trades]
    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0.0

    if std_r == 0:
        return Decimal("0")

    excess_return = mean_r - RISK_FREE_RATE_DAILY
    sharpe = (excess_return / std_r) * math.sqrt(252)
    return Decimal(str(round(sharpe, 4))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def count_hf_violations(hf_series: list[dict[str, Any]]) -> int:
    return sum(1 for day in hf_series if day["violation"])


# ---------------------------------------------------------------------------
# Slack notification (Block Kit)
# ---------------------------------------------------------------------------


def _status_emoji_and_color(
    sharpe: Decimal,
    max_drawdown: Decimal,
    hf_violations: int,
) -> tuple[str, str, str]:
    """Return (status_label, emoji, assessment) based on metric thresholds."""
    is_good = sharpe > Decimal("1") and max_drawdown < Decimal("0.20") and hf_violations == 0
    is_borderline = (
        Decimal("0.5") <= sharpe <= Decimal("1")
        or Decimal("0.20") <= max_drawdown <= Decimal("0.30")
        or 0 < hf_violations <= 3
    )

    if is_good:
        return "PASS", "green", "All metrics within acceptable thresholds."
    if is_borderline:
        return "WARN", "yellow", "Some metrics are borderline — review recommended."
    return "FAIL", "red", "One or more metrics exceed risk thresholds."


def build_slack_payload(
    date_start: str,
    date_end: str,
    win_rate: Decimal,
    sharpe: Decimal,
    max_drawdown: Decimal,
    hf_violations: int,
    n_trades: int,
    final_portfolio: Decimal,
) -> dict[str, Any]:
    status_label, _color, assessment = _status_emoji_and_color(sharpe, max_drawdown, hf_violations)

    status_icons = {"PASS": ":white_check_mark:", "WARN": ":warning:", "FAIL": ":x:"}
    icon = status_icons[status_label]

    pnl = final_portfolio - INITIAL_PORTFOLIO_USDT
    pnl_pct = (pnl / INITIAL_PORTFOLIO_USDT * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    pnl_sign = "+" if pnl >= Decimal("0") else ""

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Weekly Backtest Report - {date_start} to {date_end}",
                "emoji": True,
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{icon} *Status: {status_label}*  —  {assessment}",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Win Rate*\n`{float(win_rate) * 100:.1f}%`",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Sharpe Ratio*\n`{float(sharpe):.2f}`  _(target: >1.0)_",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Max Drawdown*\n`{float(max_drawdown) * 100:.1f}%`  _(limit: <20%)_",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*HF Violations (HF<1.6)*\n`{hf_violations} days`",
                },
            ],
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Total Trades*\n`{n_trades}`",
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Portfolio P&L (90d)*\n"
                        f"`{pnl_sign}{float(pnl):.2f} USDT ({pnl_sign}{float(pnl_pct)}%)`"
                    ),
                },
            ],
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Thresholds — Sharpe >1.0 :white_check_mark:, "
                        f"MaxDD <20% :white_check_mark:, "
                        f"HF Violations = 0 :white_check_mark:  |  "
                        f"Simulation: {SIMULATION_DAYS} days, initial capital "
                        f"{float(INITIAL_PORTFOLIO_USDT):,.0f} USDT"
                    ),
                }
            ],
        },
    ]

    return {
        "text": f"Weekly Backtest Report [{status_label}] {date_start} to {date_end}",
        "blocks": blocks,
    }


def send_slack_notification(payload: dict[str, Any]) -> bool:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("ERROR: SLACK_WEBHOOK_URL environment variable is not set.")
        return False

    try:
        response = requests.post(webhook_url, json=payload, timeout=15)
        response.raise_for_status()
        print("Slack notification sent successfully.")
        return True
    except requests.exceptions.RequestException as exc:
        print(f"ERROR: Slack notification failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Results serialisation
# ---------------------------------------------------------------------------


def build_results_dict(
    date_start: str,
    date_end: str,
    win_rate: Decimal,
    sharpe: Decimal,
    max_drawdown: Decimal,
    hf_violations: int,
    n_trades: int,
    final_portfolio: Decimal,
) -> dict[str, Any]:
    status_label, _, assessment = _status_emoji_and_color(sharpe, max_drawdown, hf_violations)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "period": {"start": date_start, "end": date_end, "days": SIMULATION_DAYS},
        "metrics": {
            "win_rate": float(win_rate),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_drawdown),
            "hf_violations": hf_violations,
            "n_trades": n_trades,
            "initial_portfolio_usdt": float(INITIAL_PORTFOLIO_USDT),
            "final_portfolio_usdt": float(final_portfolio),
        },
        "thresholds": {
            "sharpe_min": 1.0,
            "max_drawdown_limit": 0.20,
            "hf_threshold": float(HF_THRESHOLD),
            "hf_violations_limit": 0,
        },
        "status": status_label,
        "assessment": assessment,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    print(f"Running weekly backtest — {SIMULATION_DAYS}-day simulation ...")

    # Generate mock data
    trades = generate_trades()
    hf_series = generate_hf_series()

    if not trades:
        print("ERROR: No trades generated.")
        return 1

    # Calculate metrics
    win_rate = calculate_win_rate(trades)
    max_drawdown = calculate_max_drawdown(trades)
    sharpe = calculate_sharpe_ratio(trades)
    hf_violations = count_hf_violations(hf_series)
    final_portfolio = Decimal(str(trades[-1]["portfolio_value"]))
    n_trades = len(trades)

    today = datetime.now(tz=UTC).date()
    date_end = today.isoformat()
    date_start = (today - timedelta(days=SIMULATION_DAYS)).isoformat()

    # Print summary to stdout
    print(f"  Period       : {date_start} → {date_end}")
    print(f"  Trades       : {n_trades}")
    print(f"  Win Rate     : {float(win_rate) * 100:.1f}%")
    print(f"  Sharpe Ratio : {float(sharpe):.2f}")
    print(f"  Max Drawdown : {float(max_drawdown) * 100:.1f}%")
    print(f"  HF Violations: {hf_violations}")
    print(f"  Final Portfolio: {float(final_portfolio):.2f} USDT")

    # Save results to JSON
    results = build_results_dict(
        date_start,
        date_end,
        win_rate,
        sharpe,
        max_drawdown,
        hf_violations,
        n_trades,
        final_portfolio,
    )
    results_path = Path("backtest_results.json")
    try:
        with results_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {results_path}")
    except OSError as exc:
        print(f"WARNING: Could not save results file: {exc}")

    # Send Slack notification
    payload = build_slack_payload(
        date_start,
        date_end,
        win_rate,
        sharpe,
        max_drawdown,
        hf_violations,
        n_trades,
        final_portfolio,
    )
    success = send_slack_notification(payload)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
