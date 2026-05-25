"""execution_policy_safe_default

P0 GID 1214993061793196 (P3-1):
  新規ユーザーの execution_policy DB default を auto_execute → require_approval に変更。

  金融システムの安全既定は require_approval であるべき。
  role default=VIEWER + execution_policy default=auto_execute の組み合わせで
  「明示設定なし user が viewer+auto_execute」となる設計違反を修正する。

  backfill scope=全 auto_execute (role 限定なし):
    既存行のうち execution_policy='auto_execute' の全行を require_approval に修正する。
    冪等 (0件なら no-op)。
    現フェーズ(UAT 中・v4 §17 ローンチ条件3=人間承認率100%)では「正規の auto_execute」は
    存在しない前提。引継ぎ §2 で auto_execute 撲滅済 (6人全員 require_approval) のため
    既存 auto_execute 行は理論上ゼロ。viewer 以外に auto_execute が居た場合それ自体が
    想定外行であり、viewer 限定では漏れるため scope を全 auto_execute とする。

  ===========================================================================
  DEPLOY 必須前手順 (HUMAN) — 機械適用しないこと:
    本 migration を適用する *前* に、以下の SELECT を実行し結果を deploy ログに残す
    (どの行を変更するかを監査可能にするため):

      SELECT role, count(*) FROM users WHERE execution_policy='auto_execute' GROUP BY role;

  二段ゲート (HUMAN-REVIEW):
    上記 SELECT で role='viewer' 以外の auto_execute 行が 1 件でも出たら想定外。
    その場合は migration を機械適用せず claude.ai に報告して HUMAN-REVIEW を仰ぐこと。
    (migration の UPDATE 文自体は全 scope で書くが、適用するか否かの判断は人が握る)
  ===========================================================================

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change users.execution_policy DB default from auto_execute to require_approval.

    1. ALTER DEFAULT: 新規 INSERT で execution_policy 未指定の行が require_approval になる。
    2. BACKFILL: execution_policy='auto_execute' の全既存行を require_approval に修正する
       (P0 クローズ)。role 限定なし。
       現フェーズに正規 auto_execute なしの前提 (引継ぎ §2 で撲滅済)。
       冪等: 対象行が 0 件でも no-op。

    適用前に DEPLOY 必須前手順 (module docstring 参照) の SELECT 監査と
    二段ゲート (viewer 以外の auto_execute が出たら HUMAN-REVIEW) を必ず実施すること。
    """
    op.alter_column(
        "users",
        "execution_policy",
        server_default=sa.text("'require_approval'"),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
    # Backfill: 全 auto_execute 行を安全側 (require_approval) に倒す (role 限定なし)
    # NOTE: ステートメント末尾の `;` は文字列内に書かない (alembic が `--sql` 出力で
    # 自動的に `;` を付けるため、文字列に含めると `;;` の重複が出る — 動作影響なしだが
    # 見栄え悪)。
    op.execute(
        "UPDATE users SET execution_policy='require_approval' "
        "WHERE execution_policy='auto_execute'"
    )


def downgrade() -> None:
    """Revert users.execution_policy DB default back to auto_execute.

    NOTE: backfill (auto_execute → require_approval) は downgrade で戻さない。
    安全側への変更を自動で元に戻すことは金融システムとして不適切なため、意図的に省略。
    元に戻す必要がある場合は手動 SQL で対応すること。
    """
    op.alter_column(
        "users",
        "execution_policy",
        server_default=sa.text("'auto_execute'"),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
