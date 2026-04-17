# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""既存の fund_allocations レコードに tester_user_id をバックフィルするスクリプト。

Phase 1.5 マイグレーション補助ツール。
本番 DB で ALTER TABLE 後に一度だけ実行する。

Usage:
    # 対象件数の確認（DB変更なし）
    python -m scripts.backfill_tester_user_id --dry-run

    # 実際にバックフィル実行
    python -m scripts.backfill_tester_user_id --execute
"""

import argparse
import logging
import os
import sys

os.environ.setdefault("JWT_SECRET_KEY", "backfill-script-key")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.partner.allocation_models import FundAllocation  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_backfill(db: Session, *, dry_run: bool) -> None:
    """tester_user_id が未設定の fund_allocations に users.username でマッチしてバックフィル。"""
    # tester_user_id が未設定のレコードを全件取得
    pending = db.query(FundAllocation).filter(FundAllocation.tester_user_id.is_(None)).all()

    if not pending:
        logger.info("バックフィル対象なし。全レコードに tester_user_id が設定済みです。")
        return

    logger.info("バックフィル対象: %d 件", len(pending))

    matched = 0
    unmatched: list[tuple[int, str]] = []

    for alloc in pending:
        user = db.query(User).filter(User.username == alloc.tester_name).first()
        if user is None:
            logger.warning(
                "  [SKIP] allocation id=%d: tester_name=%r に一致するユーザーなし",
                alloc.id,
                alloc.tester_name,
            )
            unmatched.append((alloc.id, alloc.tester_name))
            continue

        if dry_run:
            logger.info(
                "  [DRY-RUN] allocation id=%d: tester_name=%r → tester_user_id=%d",
                alloc.id,
                alloc.tester_name,
                user.id,
            )
        else:
            alloc.tester_user_id = user.id
            logger.info(
                "  [UPDATE] allocation id=%d: tester_name=%r → tester_user_id=%d",
                alloc.id,
                alloc.tester_name,
                user.id,
            )
        matched += 1

    if not dry_run and matched > 0:
        db.commit()
        logger.info("コミット完了: %d 件を更新しました。", matched)

    if dry_run:
        logger.info("[DRY-RUN] 更新対象: %d 件 / スキップ: %d 件", matched, len(unmatched))
    else:
        logger.info("完了: 更新 %d 件 / スキップ %d 件", matched, len(unmatched))

    if unmatched:
        logger.warning("手動確認が必要なレコード（users に対応するユーザーなし）:")
        for alloc_id, name in unmatched:
            logger.warning("  allocation id=%d, tester_name=%r", alloc_id, name)


def main() -> None:
    parser = argparse.ArgumentParser(description="fund_allocations.tester_user_id バックフィル")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="変更なしで対象件数を確認")
    group.add_argument("--execute", action="store_true", help="実際にバックフィルを実行")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "sqlite:///./test.db")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()

    try:
        run_backfill(db, dry_run=args.dry_run)
    except Exception:
        logger.exception("バックフィル中にエラーが発生しました。")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
