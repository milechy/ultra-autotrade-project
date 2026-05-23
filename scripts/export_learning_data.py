#!/usr/bin/env python3
"""Export learning data (ai_decisions + features + same-session user_actions) as JSONL.

P0-6 (Hermes 受け入れ前提の学習データ層):
    1 行 = 1 ai_decision に対し、当該 decision の ai_decision_features と、
    同 session_id (もしくは同 user_id + 近接時刻) の user_actions を結合して
    1 JSONL レコードとして出力する。

設計の出典:
    docs/50_phase2_ai_optimizer_design.md §9 (学習データ層)

使い方:
    # JSONL に書き出し
    python scripts/export_learning_data.py \\
        --since 2026-05-01 --until 2026-05-23 \\
        --out /tmp/learning_dump_20260523.jsonl

    # CSV (フラット化) で書き出し
    python scripts/export_learning_data.py \\
        --since 2026-05-01 --until 2026-05-23 \\
        --out /tmp/learning_dump_20260523.csv \\
        --format csv

    # DB URL を明示
    python scripts/export_learning_data.py \\
        --since 2026-05-01 --until 2026-05-23 \\
        --out /tmp/out.jsonl \\
        --db-url postgresql://user:pass@host:5432/db

環境変数 ``DATABASE_URL`` が設定されていれば ``--db-url`` 省略可。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Iterator

# repo root を import path に追加 (backend.app.* を参照するため)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# user_actions と ai_decisions を時刻で結合する窓 (session_id 一致が無い場合に使用)
DEFAULT_USER_ACTION_WINDOW = timedelta(minutes=30)


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 date / datetime string into a tz-aware UTC datetime.

    Accepts ``YYYY-MM-DD`` (treated as 00:00:00 UTC) and full ISO datetimes.
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
        description="Export learning data (ai_decisions + features + user_actions) as JSONL/CSV."
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
        help="Output path (JSONL or CSV). Parent directory is created.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=os.environ.get("DATABASE_URL", ""),
        help="SQLAlchemy DB URL. Defaults to env DATABASE_URL.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Maximum number of ai_decisions to export (default: 10000).",
    )
    parser.add_argument(
        "--format",
        choices=("jsonl", "csv"),
        default="jsonl",
        help="Output format (default: jsonl).",
    )
    parser.add_argument(
        "--user-action-window-minutes",
        type=int,
        default=int(DEFAULT_USER_ACTION_WINDOW.total_seconds() / 60),
        help=(
            "Time window (minutes) for matching user_actions to ai_decisions "
            "when session_id is missing (default: 30)."
        ),
    )
    return parser.parse_args(argv)


def _json_default(value: Any) -> Any:
    """``json.dumps`` の default ハンドラ。Decimal / datetime を文字列化する。"""
    if isinstance(value, Decimal):
        # 学習側で float 化したいケースが多いので float に倒す。精度劣化が問題なら str に切替。
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """SQLAlchemy ORM オブジェクト → dict 変換。``_sa_instance_state`` 等は除外。"""
    if row is None:
        return {}
    result: dict[str, Any] = {}
    # __table__.columns を参照すれば private 属性を踏まずに済む
    table = getattr(row, "__table__", None)
    if table is None:
        # mappings() で取れた Row などはそのまま辞書化を試みる
        try:
            return dict(row)
        except Exception:
            return {}
    for col in table.columns:
        result[col.name] = getattr(row, col.name, None)
    return result


def iter_learning_records(
    db_url: str,
    since: datetime,
    until: datetime,
    limit: int,
    user_action_window: timedelta,
) -> Iterator[dict[str, Any]]:
    """Yield 1 dict per ai_decision in [since, until).

    Returns an iterator so callers (JSONL / CSV writers) can stream.

    Joins:
      - ai_decisions (filter by created_at)
      - LEFT JOIN ai_decision_features ON ai_decision_id
      - LEFT JOIN portfolio_snapshots ON portfolio_snapshot_id
      - sub-query: user_actions WHERE user_id matches AND
            (session_id matches when present
             OR |clicked_at - created_at| < user_action_window)
    """
    # 遅延 import: --help だけ呼ぶケースで sqlalchemy 不在でも動くようにする
    try:
        from sqlalchemy import and_, create_engine, or_, select
        from sqlalchemy.exc import OperationalError, ProgrammingError
        from sqlalchemy.orm import sessionmaker

        from app.ai.models import AIDecision
        from app.portfolio.models import PortfolioSnapshot
        from app.users.action_models import AIDecisionFeatures, UserAction
    except ImportError as exc:  # pragma: no cover - depends on runtime env
        print(
            f"ERROR: failed to import SQLAlchemy / models: {exc}\n"
            f"       run from repo root with backend deps installed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    if not db_url:
        print(
            "ERROR: DB URL not given. Pass --db-url or set DATABASE_URL env var.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    try:
        with SessionLocal() as session:
            base_stmt = (
                select(AIDecision, AIDecisionFeatures, PortfolioSnapshot)
                .join(
                    AIDecisionFeatures,
                    AIDecisionFeatures.ai_decision_id == AIDecision.id,
                    isouter=True,
                )
                .join(
                    PortfolioSnapshot,
                    PortfolioSnapshot.id == AIDecisionFeatures.portfolio_snapshot_id,
                    isouter=True,
                )
                .where(AIDecision.created_at >= since)
                .where(AIDecision.created_at < until)
                .order_by(AIDecision.created_at.asc())
                .limit(limit)
            )

            try:
                # 件数を先に取って進捗 log に使う
                rows = session.execute(base_stmt).all()
            except (OperationalError, ProgrammingError) as exc:
                print(
                    "ERROR: failed to query ai_decisions / ai_decision_features.\n"
                    "       Have the migrations been applied?\n"
                    f"       (alembic upgrade head; see backend/alembic/versions/"
                    f"h8i9j0k1l2m3_add_user_actions_and_ai_decision_features.py)\n"
                    f"       Underlying error: {exc}",
                    file=sys.stderr,
                )
                raise SystemExit(1) from exc

            total = len(rows)
            print(f"[export_learning_data] fetched {total} ai_decision row(s)", file=sys.stderr)

            for idx, (decision, features, snapshot) in enumerate(rows, start=1):
                # user_actions 取得 (per-decision クエリ。N+1 だが学習データ抽出は
                # batch 用途で頻度低、可読性優先)
                actions: list[dict[str, Any]] = []
                try:
                    if decision.user_id is not None:
                        action_window_lo = decision.created_at - user_action_window
                        action_window_hi = decision.created_at + user_action_window
                        # session_id が ai_decisions 側に存在しないため、
                        # 純粋に時間窓 + user_id でマッチする。
                        # session_id 一致条件は user_actions.session_id が
                        # 該当 decision の context と一致するロジックを将来追加可能。
                        action_stmt = (
                            select(UserAction)
                            .where(UserAction.user_id == decision.user_id)
                            .where(
                                and_(
                                    UserAction.clicked_at >= action_window_lo,
                                    UserAction.clicked_at <= action_window_hi,
                                )
                            )
                            .order_by(UserAction.clicked_at.asc())
                        )
                        for ua in session.execute(action_stmt).scalars():
                            actions.append(_row_to_dict(ua))
                except (OperationalError, ProgrammingError) as exc:
                    print(
                        "ERROR: failed to query user_actions. migrations applied?\n"
                        f"       {exc}",
                        file=sys.stderr,
                    )
                    raise SystemExit(1) from exc

                record: dict[str, Any] = {
                    "decision_id": decision.id,
                    "user_id": decision.user_id,
                    "decided_at": decision.created_at,
                    "decision": {
                        "query": decision.query,
                        "action": decision.action,
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                        "agreed": bool(decision.agreed),
                        "prompt_version": decision.prompt_version,
                    },
                    "ai_response": {
                        "primary_provider": decision.primary_provider,
                        "primary_action": decision.primary_action,
                        "primary_confidence": decision.primary_confidence,
                        "secondary_provider": decision.secondary_provider,
                        "secondary_action": decision.secondary_action,
                        "secondary_confidence": decision.secondary_confidence,
                        "rag_context_json": decision.rag_context_json,
                    },
                    "features": _row_to_dict(features) if features is not None else None,
                    "snapshot": _row_to_dict(snapshot) if snapshot is not None else None,
                    "user_actions": actions,
                }

                if idx % 100 == 0 or idx == total:
                    print(f"[{idx}/{total}] processed...", file=sys.stderr)

                yield record
    finally:
        engine.dispose()


def write_jsonl(records: Iterable[dict[str, Any]], out_path: Path) -> int:
    """Write records as JSONL. Returns the number of records written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as fp:
        for rec in records:
            fp.write(json.dumps(rec, ensure_ascii=False, default=_json_default))
            fp.write("\n")
            count += 1
    return count


def _flatten_for_csv(rec: dict[str, Any]) -> dict[str, Any]:
    """CSV 出力向けに JSON カラムを文字列化したフラット dict を返す。

    ネストした dict / list は JSON 文字列に直して 1 列にする。
    """
    flat: dict[str, Any] = {}
    for key, value in rec.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value, ensure_ascii=False, default=_json_default)
        elif isinstance(value, Decimal):
            flat[key] = float(value)
        elif isinstance(value, datetime):
            flat[key] = value.isoformat()
        else:
            flat[key] = value
    return flat


def write_csv(records: Iterable[dict[str, Any]], out_path: Path) -> int:
    """Write records as CSV (nested dict/list -> JSON string). Returns row count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    # ストリームを 1 周しないとヘッダ確定できないので buffer する。
    # --limit が default 10000 なのでメモリ的に許容。
    buffered = [_flatten_for_csv(rec) for rec in records]
    if not buffered:
        # 空ファイルでも出力 (touch 相当)
        out_path.write_text("", encoding="utf-8")
        return 0

    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in buffered:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with out_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in buffered:
            writer.writerow(row)
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.until <= args.since:
        print("ERROR: --until must be strictly greater than --since", file=sys.stderr)
        return 2

    if args.limit <= 0:
        print("ERROR: --limit must be > 0", file=sys.stderr)
        return 2

    window = timedelta(minutes=max(0, args.user_action_window_minutes))

    records = iter_learning_records(
        db_url=args.db_url,
        since=args.since,
        until=args.until,
        limit=args.limit,
        user_action_window=window,
    )

    if args.format == "csv":
        n = write_csv(records, args.out)
    else:
        n = write_jsonl(records, args.out)

    print(f"wrote {n} record(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
