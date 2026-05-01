# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/constants.py
"""auth ドメインで参照する定数 / Enum 定義。

GID 1214176344039867 (P1) で導入。

`execution_policy` の文字列リテラルがコードベース全体に散在し、
DB 側 default (`auto_execute`) と運用上の期待値 (`require_approval`) が
ずれる事故が発生したため、Enum + DB CheckConstraint + server_default で
一元化する (再発防止)。

値はハードコード文字列と完全一致する必要がある。リネーム禁止:
- DB users.execution_policy カラムに直接保存される
- API リクエスト / レスポンスで文字列として往復する
- 既存テスト・運用ドキュメントが値を直参照している
"""

from enum import Enum


class ExecutionPolicy(str, Enum):
    """ユーザーの自動執行ポリシー。

    値:
      - AUTO_EXECUTE: AI 判定後、追加承認なしに発注する (managed モード)
      - REQUIRE_APPROVAL: AI 判定で Proposal を作成し、ユーザー承認後に発注 (active モード)
      - PROPOSAL_ONLY: Proposal を作成するのみ。発注は手動 (pro モード)

    値リネーム禁止 (DB 永続化値、API 互換性のため)。
    """

    AUTO_EXECUTE = "auto_execute"
    REQUIRE_APPROVAL = "require_approval"
    PROPOSAL_ONLY = "proposal_only"

    @classmethod
    def values(cls) -> list[str]:
        """全ての有効値を文字列リストで返す。

        CheckConstraint の SQL 生成およびバリデーションで使用する。
        """
        return [member.value for member in cls]
