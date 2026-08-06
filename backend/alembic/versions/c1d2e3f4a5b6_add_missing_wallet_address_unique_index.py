"""add missing UNIQUE index on users.wallet_address

## 根本原因 (2026-08-06 調査、production 実機確認済み)

production の `users` テーブルは alembic migration を1本も実行せず、
**`Base.metadata.create_all()` + `alembic stamp` で一括作成**されたことが判明した
(全テーブルの OID がアルファベット順に連番＝ create_all の生成順そのもの。
`alembic_version` も1行のみで stamp の痕跡と整合)。

このため `alembic_version` が head を指していても、個々の migration の効果が
実際に production DB へ反映されているとは限らない (このリビジョンが直す
`ix_users_wallet_address` の欠落は、その一例)。

## alembic check が検出した production 全体のドリフト調査結果

同時に調査した alembic check の全指摘を分類した (詳細は
`docs/internal/2026-08-06_production_schema_drift_investigation.md` 参照):

- **実害があり修正が必要** → 本リビジョンで対応 (`ix_users_wallet_address` のみ)
- **命名規約の違いのみ (idx_* <-> ix_* など)、機能的には既に存在** → 触らない。
  リネームは一瞬 index/制約が消える窓を作るだけで得るものがない
- **DB 側を削除すると後退する制約** (`fund_allocations_allocated_amount_usd_check` 等)
  → 触らない。alembic check の "remove" 指示に機械的に従わない
- **モデル側が実態と異なる** (`ai_decision_features.deterministic_breakdown` の
  JSONB→JSON 変更提案等) → DB は正しい。別途モデル側を直すべき (本リビジョン対象外)
- **要判断で保留** (`smart_wallet_address` の UNIQUE 制約が二重かつ全行 UNIQUE。
  models.py の手動 SQL コメントは部分 index (`WHERE NOT NULL`) を指示しており
  実態と異なる) → 本リビジョン対象外、個別に判断する

## 本リビジョンの対象

`wallet_address` に UNIQUE index が存在しないため、**同一ウォレットアドレスを持つ
ユーザーが複数作成できる**状態だった (実測: 重複ゼロだったが、DB 制約で
守られていなかった)。資産の帰属に直結するため、これは唯一「今すぐ直すべき」実害。

型 (`VARCHAR(255)` vs models.py の `String(42)`) は最大長42文字で実害が無いため
本リビジョンでは変更しない (個別判断へ持ち越し)。

## revision ID 再採番 (2026-08-06)

初回リビジョン ID `b9c0d1e2f3a4` は、同じ親 (`a8b9c0d1e2f3`) から独立に
分岐した別PR (`add_gas_sponsored_to_transactions`) と衝突していたため
`c1d2e3f4a5b6` に採番し直し、`down_revision` を衝突相手のリビジョンへ
繋ぎ直した (production デプロイ時に `alembic upgrade head` が
"Multiple head revisions" で失敗し発覚。production への反映前に検出、
実害なし)。

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-08-06 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """wallet_address に UNIQUE index を追加する。既存データは変更しない。

    CREATE UNIQUE INDEX は重複行があると失敗するため、実行前に重複が無いことを
    前提とする (2026-08-06 production 実測で重複ゼロを確認済み)。もし重複が
    存在する環境で適用する場合は、適用前に重複を解消すること。
    """
    op.create_index(
        "ix_users_wallet_address",
        "users",
        ["wallet_address"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_wallet_address", table_name="users", if_exists=True)
