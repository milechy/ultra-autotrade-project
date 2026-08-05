#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/notifications/push.py
"""Web Push (VAPID) 通知送信実装。"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import PushSubscription

try:
    from pywebpush import WebPushException, webpush  # type: ignore

    _PYWEBPUSH_AVAILABLE = True
except ImportError:
    _PYWEBPUSH_AVAILABLE = False

logger = logging.getLogger(__name__)


class DeliveryResult(Enum):
    """1件の Web Push 送信結果。

    2026-08-05: 以前は bool だったため「購読が失効した (410)」と「一時的に失敗した
    (タイムアウト / 5xx)」を区別できず、呼び出し側が両方まとめて購読を削除していた。
    その結果 FCM の一時障害 1 回で全ユーザーの購読が消え、ユーザーが手動で再購読する
    まで通知が永久に届かなくなる (= 到達経路が黙って失われる、本プロジェクトが
    最も避けたい失敗形)。除去してよいのは FAILED_GONE のみ。
    """

    SUCCESS = "success"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_GONE = "failed_gone"


#: 購読が恒久的に消滅したことを示す HTTP status。410 が標準、404 は実装差の吸収。
_GONE_STATUS_CODES = frozenset({404, 410})


@dataclass
class VAPIDConfig:
    """VAPID 設定。秘密鍵はログに出力しないこと。"""

    public_key: str
    private_key: str
    mailto: str


class WebPushSubscription(BaseModel):
    """Web Push サブスクリプション情報。"""

    endpoint: str
    p256dh: str
    auth: str
    # 2026-08-04 PR3: どのユーザーの購読かを紐付ける。router 側で require_active_user
    # 経由の current_user.id を必ず設定する。既存 3 フィールドのみの呼び出し (テスト等) との
    # 後方互換のため Optional のまま維持する。
    user_id: Optional[int] = None


class InMemorySubscriptionStore:
    """スレッドセーフなインメモリ Push サブスクリプションストア。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # endpoint をキーとして重複を防ぐ
        self._subscriptions: dict[str, WebPushSubscription] = {}

    def add(self, subscription: WebPushSubscription) -> None:
        """サブスクリプションを追加する。同じ endpoint は上書きする。"""
        with self._lock:
            self._subscriptions[subscription.endpoint] = subscription

    def remove(self, endpoint: str) -> None:
        """指定 endpoint のサブスクリプションを削除する。存在しない場合は無視。"""
        with self._lock:
            self._subscriptions.pop(endpoint, None)

    def get_all(self) -> list[WebPushSubscription]:
        """全サブスクリプションを返す。"""
        with self._lock:
            return list(self._subscriptions.values())

    def get_for_user(self, user_id: int) -> list[WebPushSubscription]:
        """指定ユーザーのサブスクリプションのみを返す (WebPushSender.send_to_user が使用)。"""
        with self._lock:
            return [s for s in self._subscriptions.values() if s.user_id == user_id]

    def count(self) -> int:
        """登録済みサブスクリプション数を返す。"""
        with self._lock:
            return len(self._subscriptions)


class SubscriptionStore(Protocol):
    """WebPushSender が要求するストアの構造的インターフェース。

    2026-08-04 PR3: InMemorySubscriptionStore (テスト用) と DatabaseSubscriptionStore
    (本番用、DB永続化) の両方がこの形を満たす。WebPushSender 自体は変更しない。
    """

    def add(self, subscription: WebPushSubscription) -> None: ...
    def remove(self, endpoint: str) -> None: ...
    def get_all(self) -> list[WebPushSubscription]: ...
    def get_for_user(self, user_id: int) -> list[WebPushSubscription]: ...
    def count(self) -> int: ...


class DatabaseSubscriptionStore:
    """push_subscriptions テーブルに永続化するストア。

    2026-08-05: 以前は users.notification_settings_json (TEXT) の push_subscriptions
    キーに JSON 配列として保存していた。しかし同じセルに通知設定
    (push_enabled / preferences) が同居し、双方が read-modify-write で別セッションから
    書くため lost update が発生していた (購読 1 件、または設定変更 1 回が黙って消える)。
    専用テーブルに分離したことで read-modify-write が無くなり、問題クラス自体が消えた。

    endpoint のグローバル一意性は UNIQUE 制約が保証する (旧実装は全ユーザー走査で
    模倣していた)。通知設定は引き続き notification_settings_json 側にあり、
    本ストアはそれに一切触れない。
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_schema(row: PushSubscription) -> WebPushSubscription:
        return WebPushSubscription(
            endpoint=row.endpoint,
            p256dh=row.p256dh,
            auth=row.auth,
            user_id=row.user_id,
        )

    def add(self, subscription: WebPushSubscription) -> None:
        """購読を保存する。同一 endpoint は (他ユーザー分も含め) 付け替える。

        DELETE → INSERT を 1 トランザクションで行う。**この順序は変更しないこと**:
        逆順にすると endpoint が一時的に 2 ユーザーへ属する窓ができ、
        同一端末で別アカウントにログインした際に旧ユーザー宛の通知
        (金額・資産情報) が届きうる (I-12)。
        """
        if subscription.user_id is None:
            logger.warning(
                "DatabaseSubscriptionStore.add: user_id が未設定のため保存をスキップしました "
                "(endpoint=%s)",
                subscription.endpoint[:30],
            )
            return

        for attempt in (1, 2):
            db = self._session_factory()
            try:
                db.execute(
                    delete(PushSubscription).where(
                        PushSubscription.endpoint == subscription.endpoint
                    )
                )
                db.add(
                    PushSubscription(
                        endpoint=subscription.endpoint,
                        user_id=subscription.user_id,
                        p256dh=subscription.p256dh,
                        auth=subscription.auth,
                    )
                )
                db.commit()
                return
            except IntegrityError:
                # 同一 endpoint を別リクエストが同時に INSERT した (稀) か、
                # user_id が存在しない (FK 違反)。前者は 1 回リトライで収束する。
                db.rollback()
                if attempt == 2:
                    logger.warning(
                        "DatabaseSubscriptionStore.add: 保存できませんでした "
                        "(user_id=%s endpoint=%s)",
                        subscription.user_id,
                        subscription.endpoint[:30],
                    )
                    raise
            finally:
                db.close()

    def remove(self, endpoint: str) -> None:
        """指定 endpoint の購読を削除する。存在しない場合は何もしない。"""
        db = self._session_factory()
        try:
            db.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))
            db.commit()
        finally:
            db.close()

    def get_all(self) -> list[WebPushSubscription]:
        """全ユーザーの全購読を返す (WebPushSender.send_to_all 用)。"""
        db = self._session_factory()
        try:
            rows = db.scalars(select(PushSubscription)).all()
            return [self._to_schema(r) for r in rows]
        finally:
            db.close()

    def get_for_user(self, user_id: int) -> list[WebPushSubscription]:
        """指定ユーザーの購読のみを返す (WebPushSender.send_to_user が使用)。"""
        db = self._session_factory()
        try:
            rows = db.scalars(
                select(PushSubscription).where(PushSubscription.user_id == user_id)
            ).all()
            return [self._to_schema(r) for r in rows]
        finally:
            db.close()

    def count(self) -> int:
        """登録済み購読の総数を返す。"""
        db = self._session_factory()
        try:
            return db.scalar(select(func.count()).select_from(PushSubscription)) or 0
        finally:
            db.close()


class WebPushSender:
    """Web Push (VAPID) 通知送信クラス。"""

    def __init__(self, vapid_config: VAPIDConfig, store: SubscriptionStore) -> None:
        self._vapid_config = vapid_config
        self._store = store

    def send_to_all(self, payload: dict[str, Any], ttl: int = 86400) -> int:
        """全サブスクリプションに通知を送信する。成功数を返す。"""
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush がインストールされていません。Web Push は無効です。")
            return 0

        subscriptions = self._store.get_all()
        success_count = 0
        failed_count = 0
        gone_endpoints: list[str] = []

        for subscription in subscriptions:
            result = self._deliver_guarded(subscription, payload, ttl)
            if result is DeliveryResult.SUCCESS:
                success_count += 1
                continue
            failed_count += 1
            if result is DeliveryResult.FAILED_GONE:
                gone_endpoints.append(subscription.endpoint)

        self._purge_gone(gone_endpoints)

        logger.info(
            "Web Push 送信完了: 成功=%d, 失敗=%d, 失効除去=%d, 合計=%d",
            success_count,
            failed_count,
            len(gone_endpoints),
            len(subscriptions),
        )
        return success_count

    def send_to_user(self, user_id: int, payload: dict[str, Any], ttl: int = 86400) -> bool:
        """特定ユーザーの全端末へ配信する。1件でも成功すれば True。購読が無ければ False。

        2026-08-04 PR5: send_to_all のユーザー限定版。AI提案通知等の per-user 配信に使う
        (send_to_all は router.py の /push/test 専用のまま変更しない)。
        """
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush がインストールされていません。Web Push は無効です。")
            return False

        subscriptions = self._store.get_for_user(user_id)
        success = False
        gone_endpoints: list[str] = []

        for subscription in subscriptions:
            result = self._deliver_guarded(subscription, payload, ttl)
            if result is DeliveryResult.SUCCESS:
                success = True
            elif result is DeliveryResult.FAILED_GONE:
                gone_endpoints.append(subscription.endpoint)

        self._purge_gone(gone_endpoints)
        return success

    def _deliver_guarded(
        self, subscription: WebPushSubscription, payload: dict[str, Any], ttl: int
    ) -> DeliveryResult:
        """send_to_subscription を例外から守る。原因不明の例外は一時失敗として扱う。

        「失効と断定できない失敗」で購読を捨てないことが要件 (B-E1 / B-E2)。
        """
        try:
            return self.send_to_subscription(subscription, payload, ttl)
        except Exception:
            logger.exception(
                "Web Push 送信中に予期しないエラーが発生しました (購読は保持): endpoint=%s",
                subscription.endpoint[:30],
            )
            return DeliveryResult.FAILED_TRANSIENT

    def _purge_gone(self, gone_endpoints: list[str]) -> None:
        """失効した購読のみをストアから除去する。

        除去は「次回の無駄打ちを減らす」だけの後片付けなので、失敗しても
        配信結果 (戻り値) に影響させてはならない。以前は例外がそのまま
        send_to_user / send_to_all を貫通し、呼び出し元 (_deliver_ai_proposal_push)
        の広い except に捕まって **配信できたのに delivered 記録が残らない**
        状態を作っていた (「送信した/到達した」を測るための列が欠ける = 可観測性の穴)。
        1 件の除去失敗が他の除去も止めないよう、endpoint 単位で捕捉する。
        """
        for endpoint in gone_endpoints:
            try:
                self._store.remove(endpoint)
            except Exception:
                logger.exception(
                    "失効した購読の除去に失敗しました (配信結果には影響させない): endpoint=%s",
                    endpoint[:30],
                )
                continue
            logger.info("失効した購読を除去しました: endpoint=%s", endpoint[:30])

    def send_to_subscription(
        self, subscription: WebPushSubscription, payload: dict[str, Any], ttl: int
    ) -> DeliveryResult:
        """特定のサブスクリプションに送信し、結果を3分類して返す。

        2026-08-05: 戻り値を bool から DeliveryResult に変更。呼び出し側が
        「失効 (削除すべき)」と「一時失敗 (残すべき)」を区別できるようにするため。
        """
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush がインストールされていません。Web Push は無効です。")
            return DeliveryResult.FAILED_TRANSIENT

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=self._vapid_config.private_key,
                vapid_claims={"sub": f"mailto:{self._vapid_config.mailto}"},
                ttl=ttl,
            )
            logger.info("Web Push 送信成功: endpoint=%s", subscription.endpoint[:30])
            return DeliveryResult.SUCCESS
        except Exception as exc:  # noqa: BLE001
            status_code: Optional[int] = None
            if _PYWEBPUSH_AVAILABLE:
                if isinstance(exc, WebPushException) and exc.response is not None:
                    status_code = exc.response.status_code

            # 404/410 のみが「購読はもう存在しない」を意味する。それ以外 (5xx / 429 /
            # ネットワーク断 / status 不明) は購読が生きている可能性があるため残す。
            if status_code in _GONE_STATUS_CODES:
                logger.info(
                    "Web Push サブスクリプション失効 (status=%s): endpoint=%s",
                    status_code,
                    subscription.endpoint[:30],
                )
                return DeliveryResult.FAILED_GONE

            logger.error(
                "Web Push 送信失敗 (一時エラー扱い・購読は保持): status=%s, endpoint=%s",
                status_code,
                subscription.endpoint[:30],
            )
            return DeliveryResult.FAILED_TRANSIENT


def push_allowed_for_user(raw_settings_json: Optional[str], preference_key: str) -> bool:
    """ユーザーの通知設定が当該種別の Web Push を許可しているか判定する。

    2026-08-05 (受け入れ条件 B-N4): 「通知設定で提案通知を無効にする → 配信されない」。
    以前は購読行が存在すれば設定を無視して送っていたため、設定画面で OFF にしても
    通知が届く状態だった (設定表示と実挙動の乖離 = 本プロジェクトが繰り返している
    ドリフトと同型)。

    push_enabled は NotificationSettingsModel 既定が False であり、
    「明示的に有効化していないユーザーには送らない」を既定の約束とする。
    設定が壊れている場合も送らない (fail-closed: 意図しない通知より無通知を選ぶ。
    到達経路ゼロ側は別途 B-6 の検知対象になる)。
    """
    if not raw_settings_json:
        return False
    try:
        raw = json.loads(raw_settings_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(raw, dict):
        return False
    if raw.get("push_enabled") is not True:
        return False
    preferences = raw.get("preferences")
    if isinstance(preferences, dict) and preferences.get(preference_key) is False:
        return False
    return True


def get_vapid_config() -> Optional[VAPIDConfig]:
    """環境変数から VAPID 設定を読み込む。未設定なら None を返す。

    VAPID_SUBJECT (例: mailto:admin@example.com) または VAPID_MAILTO を受け付ける。
    """
    public_key = os.getenv("VAPID_PUBLIC_KEY")
    private_key = os.getenv("VAPID_PRIVATE_KEY")
    # VAPID_SUBJECT (標準名) と VAPID_MAILTO (旧名) の両方をサポート
    subject = os.getenv("VAPID_SUBJECT") or os.getenv("VAPID_MAILTO")
    # "mailto:" プレフィックスは vapid_claims 内で付加するため除去
    mailto = subject.removeprefix("mailto:") if subject else None

    if not public_key or not private_key or not mailto:
        logger.debug("VAPID 設定が未設定のため Web Push は無効です。")
        return None

    return VAPIDConfig(
        public_key=public_key,
        private_key=private_key,
        mailto=mailto,
    )
