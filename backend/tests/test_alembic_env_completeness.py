# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_alembic_env_completeness.py
"""alembic/env.py のモデル import 完全性ガード。

import 漏れがあると Base.metadata がそのテーブルを認識せず、autogenerate が
実在テーブルを「removed」と誤検出して DROP TABLE を生成する(本番スキーマ破壊リスク)。
新規モデルモジュール追加時に env.py への import 追加を強制する回帰テスト。
2026-06-25: notification_logs / fund_allocations / chat_messages / fee_allowances /
ai_feedbacks の 5 テーブルが env.py 未 import で alembic check WARNING を出していた事象の再発防止。
"""

import glob
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent


def _module_path(file_path: str) -> str:
    """app/x/y.py -> app.x.y"""
    rel = Path(file_path).resolve().relative_to(_BACKEND)
    return str(rel.with_suffix("")).replace("/", ".")


def test_env_py_imports_every_model_module() -> None:
    """__tablename__ を宣言する全モジュールが alembic/env.py で import されていること。"""
    env_src = (_BACKEND / "alembic" / "env.py").read_text(encoding="utf-8")

    model_modules: set[str] = set()
    for f in glob.glob(str(_BACKEND / "app" / "**" / "*.py"), recursive=True):
        if "test" in f:
            continue
        if "__tablename__" in Path(f).read_text(encoding="utf-8"):
            model_modules.add(_module_path(f))

    missing = sorted(m for m in model_modules if f"from {m} import" not in env_src)
    assert not missing, (
        "alembic/env.py が import していないモデルモジュール: "
        f"{missing}。autogenerate が当該テーブルを DROP 誤生成する。env.py に import を追加すること。"
    )


def test_base_metadata_covers_all_declared_tables() -> None:
    """env.py の import 集合で Base.metadata が全 __tablename__ を網羅すること(機能確認)。"""
    # env.py が import する全モジュールを import (env.py と同一集合)
    import app.ai.feedback_models  # noqa: F401
    import app.ai.models  # noqa: F401
    import app.auth.models  # noqa: F401
    import app.chat.models  # noqa: F401
    import app.fees.allowance_models  # noqa: F401
    import app.fees.models  # noqa: F401
    import app.invitations.models  # noqa: F401
    import app.knowledge.models  # noqa: F401
    import app.notifications.models  # noqa: F401
    import app.partner.allocation_models  # noqa: F401
    import app.portfolio.models  # noqa: F401
    import app.proposals.models  # noqa: F401
    import app.tos.models  # noqa: F401
    import app.transactions.models  # noqa: F401
    import app.users.models  # noqa: F401
    from app.database import Base

    registered = set(Base.metadata.tables.keys())

    declared: set[str] = set()
    for f in glob.glob(str(_BACKEND / "app" / "**" / "*.py"), recursive=True):
        if "test" in f:
            continue
        for name in re.findall(
            r"__tablename__\s*=\s*[\"']([a-z_]+)[\"']", Path(f).read_text(encoding="utf-8")
        ):
            declared.add(name)

    missing = sorted(declared - registered)
    assert not missing, f"Base.metadata に未登録のテーブル: {missing}"
