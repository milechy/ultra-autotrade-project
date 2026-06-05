# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/execution_route.py
"""提案の執行経路 (CEX 本線 / on-chain Aave opt-in) の定義と誤執行ガード。

P0-2 (Asana 1215364069502631) で導入。

§14a 同型の「どの経路で誰の資産が動くか」取り違えリスクを構造的に防ぐ:
  - proposal ごとに execution_route を作成時に確定し immutable に保持する
    (immutability は models.py の SQLAlchemy set イベントで強制する)。
  - CEX 経路は CEX API レスポンス + order_id を DB 記録し、on-chain tx_hash は
    一切持たない (basescan に現れない = 正常)。
  - on-chain 経路は P0-1 同様 tx_hash / from / to を receipt 検証し、
    proposal_id ↔ tx_hash を DB に紐付ける。
  - 経路と執行証跡が食い違った場合 (on-chain 選択 proposal が CEX 経路で執行、
    逆も) は即時 EMERGENCY アラート + 例外送出で自動進行を止め、手動介入を必須化する。

値リネーム禁止: DB proposals.execution_route カラムに直接保存され、API で文字列
として往復し、CHECK 制約 / migration が値を直参照する (auth/constants.py の
ExecutionPolicy と同じ規律)。
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - 型補完用
    from .models import Proposal

logger = logging.getLogger(__name__)


class ExecutionRoute(str, Enum):
    """proposal の執行経路。

    値:
      - ONCHAIN_AAVE: on-chain Aave V3 経路 (opt-in)。partner wallet が署名し
        basescan に tx_hash が現れる。
      - CEX: CEX (Bybit 等) 経路 (本線)。CEX API で発注し order_id / レスポンスを
        記録する。basescan には一切現れない。

    値リネーム禁止 (DB 永続化値・API 互換性のため)。
    """

    ONCHAIN_AAVE = "onchain_aave"
    CEX = "cex"

    @classmethod
    def values(cls) -> list[str]:
        """全ての有効値を文字列リストで返す (CheckConstraint / バリデーション用)。"""
        return [member.value for member in cls]


# proposals.execution_route のデフォルト。既存運用は Aave 単独だったため
# 後方互換 (既存行 / 経路未指定の新規行) は on-chain Aave とみなす。
DEFAULT_EXECUTION_ROUTE: str = ExecutionRoute.ONCHAIN_AAVE.value


class RouteMismatchError(Exception):
    """proposal の execution_route と実際の執行証跡が食い違った時に送出する。

    誤執行 (別経路で執行された) を意味し、自動進行を止めて手動介入を必須化する。
    """


def detect_route_mismatch(
    route: str,
    *,
    has_onchain_tx: bool,
    has_cex_order: bool,
) -> Optional[str]:
    """execution_route と執行証跡の不整合を検出する。

    :param route: proposal.execution_route の値
    :param has_onchain_tx: on-chain tx_hash (basescan 証跡) が存在するか
    :param has_cex_order: CEX order_id / レスポンスが存在するか
    :returns: 不整合があれば人間可読な説明文字列、無ければ None

    判定:
      - CEX 経路なのに on-chain tx_hash がある → 誤執行 (本来 basescan に現れない)
      - ONCHAIN_AAVE 経路なのに CEX order がある → 誤執行 (本来 CEX を使わない)
    """
    if route == ExecutionRoute.CEX.value and has_onchain_tx:
        return (
            "CEX 経路の proposal に on-chain tx_hash (basescan 証跡) が記録された。"
            "CEX 経路は basescan に一切現れないのが正常 (誤執行の疑い)。"
        )
    if route == ExecutionRoute.ONCHAIN_AAVE.value and has_cex_order:
        return (
            "on-chain Aave 経路の proposal に CEX order/レスポンスが記録された。"
            "on-chain 経路は CEX API を使わないのが正常 (誤執行の疑い)。"
        )
    return None


def notify_route_mismatch(proposal_id: int, route: str, detail: str) -> None:
    """誤執行を管理者へ即時 EMERGENCY 通知する (通知失敗で本処理を止めない)。

    手動介入必須を明示する文面を含める。
    """
    try:
        from app.notifications.factory import get_notification_service  # noqa: PLC0415
        from app.notifications.schemas import (  # noqa: PLC0415
            NotificationChannel,
            NotificationMessage,
            NotificationSeverity,
        )

        message = NotificationMessage(
            channel=NotificationChannel.SLACK,
            severity=NotificationSeverity.EMERGENCY,
            title=f"🚨 誤執行検出 (proposal #{proposal_id})",
            body=(
                f"proposal_id: {proposal_id}\n"
                f"execution_route: {route}\n"
                f"detail: {detail}\n"
                "action: 自動進行を停止しました。手動介入必須 "
                "(資産が別経路/別 partner wallet で動いた可能性、即時確認)。"
            ),
        )
        get_notification_service().send(message)
    except Exception:  # noqa: BLE001 — 通知失敗で本処理を止めない
        logger.exception(
            "proposal %d: failed to send route-mismatch EMERGENCY notification", proposal_id
        )


def assert_route(
    proposal: "Proposal",
    expected: ExecutionRoute,
) -> None:
    """proposal がこれから執行しようとする経路 (expected) と一致するか確認する。

    一致しなければ誤執行とみなし、即時 EMERGENCY 通知 + RouteMismatchError 送出で
    自動進行を止める (手動介入必須)。

    submit-tx (on-chain) / record_cex_execution (CEX) の入口で呼び、
    「on-chain 選択 proposal を CEX 経路で執行」「逆」を構造的に弾く。
    """
    route = proposal.execution_route or DEFAULT_EXECUTION_ROUTE
    if route == expected.value:
        return
    detail = f"proposal.execution_route={route} だが {expected.value} 経路で執行されようとした"
    notify_route_mismatch(proposal.id, route, detail)
    raise RouteMismatchError(detail)


def record_cex_execution(
    proposal: "Proposal",
    *,
    cex_order_id: str,
    cex_response: str,
) -> None:
    """CEX 経路の執行完了を proposal に記録する。

    - execution_route が CEX であることを assert_route で確認 (違えば誤執行アラート + 例外)。
    - CEX API レスポンス + order_id (tx_id) を DB に記録する。
    - on-chain tx_hash は設定しない (basescan に現れないのが正常)。

    呼び出し元が db.commit() を行う責務を持つ。
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    assert_route(proposal, ExecutionRoute.CEX)
    proposal.cex_order_id = cex_order_id
    proposal.cex_response = cex_response
    proposal.status = "executed"
    proposal.executed_at = datetime.now(timezone.utc)
    logger.info(
        "proposal %d: CEX execution recorded order_id=%s (no on-chain tx, basescan clean)",
        proposal.id,
        cex_order_id,
    )
