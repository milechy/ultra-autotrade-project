# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
T1-B + T1-C simulation against historical ai_decisions reasons.

Replays the past N days of staging ai_decisions through each candidate variant
of the T1-B (neutral relaxation) and T1-C (macro lift) changes and reports how
many decisions would have cleared the AND-condition guard for BUY and for SELL.

Inputs
------
A JSONL file where each line is one historical decision with the fields that
the agents/guard depend on:

    {
      "ai_decision_id": 574,
      "created_at": "2026-05-28T05:42:44Z",
      "indicator": {"bias": "neutral", "confidence": 42},
      "macro":     {"bias": "neutral", "confidence": 25,
                    "key_data": {"fed_stance": "neutral",
                                 "news_sentiment": "neutral"}},
      "raw_macro_score_inputs": {"fed_stance": "neutral",
                                 "news_sentiment": "neutral",
                                 "news_has_summary": false}
    }

`raw_macro_score_inputs` is what T1-C variants recompute the macro signal from.
If only the post-agent values are available, the script falls back to the macro
fields and skips T1-C variants for that row.

Producing the JSONL on the production VPS (see [[staging-lives-on-prod-vps]]):

    docker exec -i postgres psql -U postgres -d ultra_autotrade -At -F$'\t' \
        -c "SELECT ai_decision_id, created_at, primary_action, confidence, reason
            FROM ai_decisions
            WHERE created_at >= now() - interval '7 days'
            ORDER BY ai_decision_id"  > rows.tsv

Then parse `reason` (which embeds the per-agent breakdown) into the JSONL form
above and feed it to this script.

Usage
-----
    python scripts/simulate_t1bc_relaxation.py rows.jsonl

Reports a table of (variant, BUY-pass count, SELL-pass count) so a reviewer can
weigh how much each option opens up the BUY path while keeping SELL fenced.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Pure-local re-implementations so the script can run without importing the
# app package (useful for reviewers reading the diff without a venv).
_DIRECTIONAL_THRESHOLD = 70


@dataclass(frozen=True)
class Variant:
    name: str
    bullish_relax: frozenset[str]
    bearish_relax: frozenset[str]
    neutral_macro_lift: int  # added to macro score only when fed_stance == "neutral"


VARIANTS: list[Variant] = [
    # Baseline (production today): unknown-only relax, no macro lift.
    Variant("baseline", frozenset({"unknown"}), frozenset({"unknown"}), 0),
    # B1+C1 (recommended in the PR): asymmetric neutral relax + mild +5.
    Variant("B1+C1", frozenset({"unknown", "neutral"}), frozenset({"unknown"}), 5),
    # B1+C2: same asymmetry, larger lift +10.
    Variant("B1+C2", frozenset({"unknown", "neutral"}), frozenset({"unknown"}), 10),
    # B1+C3: asymmetric + aggressive +20 (close to "dovish" weight).
    Variant("B1+C3", frozenset({"unknown", "neutral"}), frozenset({"unknown"}), 20),
    # B2+C1: symmetric neutral relax (BOTH BUY and SELL) + mild lift.
    Variant("B2+C1", frozenset({"unknown", "neutral"}), frozenset({"unknown", "neutral"}), 5),
    # B2+C3: symmetric + aggressive (worst-case #365-exposure scenario).
    Variant("B2+C3", frozenset({"unknown", "neutral"}), frozenset({"unknown", "neutral"}), 20),
]


def _recompute_macro(raw: dict, neutral_lift: int) -> tuple[str, int]:
    """Recompute (bias, confidence) for the macro agent under a given neutral_lift.

    Mirrors agents.macro_agent rules exactly. Returns (bias, confidence).
    """
    fed = raw.get("fed_stance")
    sentiment = raw.get("news_sentiment")
    has_summary = bool(raw.get("news_has_summary"))

    score = 50
    if has_summary and sentiment == "positive":
        score += 15
    elif has_summary and sentiment == "negative":
        score -= 15

    if fed == "dovish":
        score += 20
    elif fed == "hawkish":
        score -= 15
    elif fed == "neutral":
        score += neutral_lift

    if score >= 65:
        bias = "bullish"
    elif score <= 35:
        bias = "bearish"
    else:
        bias = "neutral"
    confidence = min(85, max(25, abs(score - 50) * 2 + 25))
    return bias, confidence


def _agree(
    ind_bias: str,
    ind_conf: int,
    mac_bias: str,
    mac_conf: int,
    fed_stance: str | None,
    direction: str,
    relax: frozenset[str],
) -> bool:
    """Replicates MultiAgentContext.indicator_and_macro_agree_{bullish,bearish}."""
    if ind_bias is None or mac_bias is None:
        return False
    if fed_stance in relax:
        return ind_bias == direction and ind_conf >= _DIRECTIONAL_THRESHOLD
    return (
        ind_bias == direction
        and ind_conf >= _DIRECTIONAL_THRESHOLD
        and mac_bias == direction
        and mac_conf >= _DIRECTIONAL_THRESHOLD
    )


def evaluate_row(row: dict, variant: Variant) -> tuple[bool, bool]:
    """Return (bullish_pass, bearish_pass) under the given variant."""
    ind = row["indicator"]
    macro = row["macro"]
    raw = row.get("raw_macro_score_inputs")

    if raw and variant.neutral_macro_lift != 0:
        mac_bias, mac_conf = _recompute_macro(raw, variant.neutral_macro_lift)
        fed = raw.get("fed_stance")
    else:
        mac_bias = macro["bias"]
        mac_conf = macro["confidence"]
        fed = (macro.get("key_data") or {}).get("fed_stance")

    bull = _agree(
        ind["bias"], ind["confidence"], mac_bias, mac_conf, fed, "bullish", variant.bullish_relax
    )
    bear = _agree(
        ind["bias"], ind["confidence"], mac_bias, mac_conf, fed, "bearish", variant.bearish_relax
    )
    return bull, bear


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to ai_decisions JSONL")
    args = parser.parse_args(list(argv))

    rows: list[dict] = []
    with args.input.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("No rows in input.", file=sys.stderr)
        return 2

    print(f"Replaying {len(rows)} ai_decisions rows across {len(VARIANTS)} variants.\n")
    print(f"{'variant':<12} {'BUY pass':>10} {'SELL pass':>11} {'BUY %':>8} {'SELL %':>8}")
    print("-" * 54)
    for v in VARIANTS:
        bulls = sum(1 for r in rows if evaluate_row(r, v)[0])
        bears = sum(1 for r in rows if evaluate_row(r, v)[1])
        print(
            f"{v.name:<12} {bulls:>10} {bears:>11} "
            f"{bulls / len(rows) * 100:>7.1f}% {bears / len(rows) * 100:>7.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
