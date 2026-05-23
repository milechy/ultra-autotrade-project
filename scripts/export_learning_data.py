#!/usr/bin/env python3
"""Export learning data (ai_decisions + features + same-session user_actions) as JSONL.

P0-6 (Hermes 受け入れ前提の学習データ層):
    1 行 = 1 ai_decision に対し、当該 decision の ai_decision_features と、
    同 session_id (もしくは同 user_id + 近接時刻) の user_actions を結合して
    1 JSONL レコードとして出力する。

このスクリプトは骨格 (skeleton) のみ。実装本体は後続タスクで埋める。
docs/50_phase2_ai_optimizer_design.md §9 (学習データ層) を設計の出典とする。

使い方:
    python scripts/export_learning_data.py \\
        --since 2026-05-01 --until 2026-05-23 \\
        --out /tmp/learning_dump_20260523.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 date / datetime string into a tz-aware UTC datetime.

    Accepts "YYYY-MM-DD" (treated as 00:00:00 UTC) and full ISO datetimes.
    """
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--since/--until must be ISO-8601 (YYYY-MM-DD or full datetime); got {value!r}"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export learning data (ai_decisions + features + user_actions) as JSONL."
    )
    parser.add_argument(
        "--since",
        type=_parse_iso,
        required=True,
        help="Inclusive lower bound on ai_decisions.created_at (ISO-8601).",
    )
    parser.add_argument(
        "--until",
        type=_parse_iso,
        required=True,
        help="Exclusive upper bound on ai_decisions.created_at (ISO-8601).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSONL path (will be created/overwritten).",
    )
    return parser.parse_args(argv)


def iter_learning_records(since: datetime, until: datetime) -> Iterable[dict[str, Any]]:
    """Yield 1 dict per ai_decision in [since, until).

    TODO: implement using SQLAlchemy session.
        - SELECT ai_decisions WHERE created_at >= :since AND created_at < :until
        - LEFT JOIN ai_decision_features ON ai_decision_id
        - LEFT JOIN portfolio_snapshots ON portfolio_snapshot_id
        - LEFT JOIN user_actions ON (user_id matches AND
              (session_id = ai_decisions.session_id when present,
               OR |clicked_at - decisions.created_at| < window))
        - Yield: {
            "ai_decision_id": ...,
            "user_id": ...,
            "created_at": ISO,
            "query": ..., "action": ..., "confidence": ...,
            "features": {...},                 # from ai_decision_features
            "portfolio_snapshot": {...} | None,
            "user_actions": [ {...}, ... ],    # 同 session/近接時刻
          }
    """
    # TODO: implement
    return []


def write_jsonl(records: Iterable[dict[str, Any]], out_path: Path) -> int:
    """Write records as JSONL. Returns the number of records written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as fp:
        for rec in records:
            fp.write(json.dumps(rec, ensure_ascii=False, default=str))
            fp.write("\n")
            count += 1
    return count


def main() -> int:
    args = parse_args()
    if args.until <= args.since:
        print("ERROR: --until must be strictly greater than --since", file=sys.stderr)
        return 2

    # TODO: bootstrap SQLAlchemy session from backend/app/database.py
    records = iter_learning_records(args.since, args.until)
    n = write_jsonl(records, args.out)
    print(f"wrote {n} record(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
