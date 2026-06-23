# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/privy/delegation_service.py
"""委譲枠 → Privy policy 作成のサービス層（v4 Phase 2-D-B.2 / L1 配線）。

`/api/user/delegation/prepare` が呼ぶ薄いサービス。委譲枠のパラメータから Privy policy を
組み立て（[[policy_mapper]]）、実 Privy に作成（[[rest_client]] `create_policy`）して
``(policy_id, signer_id)`` を返す。

**dormant（既定で無効）**: 以下が全て揃わない限り `prepare_delegation_policy` は
`DelegationPolicyNotEnabledError` を送出し、Privy を一切叩かない。本番は現状いずれも未設定の
ため inert（L0 実登録 + フラグ ON で初めて有効化される）::

    DELEGATION_PRIVY_POLICY_ENABLED=true   # 明示フラグ（既定 false）
    PRIVY_SERVER_SIGNER_ID=<key quorum id> # L0 で登録した SERVER_SIGNER_ID
    PRIVY_APP_ID / PRIVY_APP_SECRET        # Privy 認証（PrivyRestClient が要求）

二重ガード（Privy policy(TEE) + backend 2-A ゲート）の Privy 側を組む層。% 上限・出金除外は
backend 側で enforce する（policy_mapper docstring 参照）。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from app.aave.chains import get_active_chains
from app.privy.policy_mapper import PolicyMappingError, build_delegation_policy
from app.privy.rest_client import PrivyRestClient, PrivyRestError

logger = logging.getLogger(__name__)

_FLAG_ENV = "DELEGATION_PRIVY_POLICY_ENABLED"
_SIGNER_ID_ENV = "PRIVY_SERVER_SIGNER_ID"


class DelegationPolicyNotEnabledError(RuntimeError):
    """委譲 policy 作成が未有効化（フラグ未設定 / L0 未登録 / Privy creds 不足）。"""


class DelegationPolicyError(RuntimeError):
    """委譲 policy 作成に失敗した（写像不能 / Privy エラー）。"""


def _flag_enabled() -> bool:
    return os.getenv(_FLAG_ENV, "false").strip().lower() == "true"


def get_server_signer_id() -> str:
    """L0 で登録した SERVER_SIGNER_ID（未設定なら空文字）。"""
    return os.getenv(_SIGNER_ID_ENV, "").strip()


def is_delegation_policy_enabled() -> bool:
    """委譲 policy 作成が有効か（フラグ + L0 signer id + Privy creds が揃うか）。"""
    return bool(
        _flag_enabled()
        and get_server_signer_id()
        and os.getenv("PRIVY_APP_ID")
        and os.getenv("PRIVY_APP_SECRET")
    )


def resolve_delegation_chain_name() -> str:
    """委譲 policy を作る対象チェーン名（先頭の active chain）。

    本番=base / staging-v4=base_sepolia（AAVE_ACTIVE_CHAINS 由来）。
    """
    return get_active_chains()[0].chain_name


def prepare_delegation_policy(
    *,
    wallet_address: str,
    allowed_protocols: list[str],
    expires_at: datetime,
    chain_name: str | None = None,
) -> tuple[str, str]:
    """委譲枠 → Privy policy を作成し ``(policy_id, signer_id)`` を返す。

    :raises DelegationPolicyNotEnabledError: dormant（未有効化）時
    :raises DelegationPolicyError: 写像不能 / Privy 作成失敗
    """
    if not is_delegation_policy_enabled():
        raise DelegationPolicyNotEnabledError(
            "delegation policy preparation is not enabled "
            "(set DELEGATION_PRIVY_POLICY_ENABLED + PRIVY_SERVER_SIGNER_ID after L0)"
        )

    chain = chain_name or resolve_delegation_chain_name()
    try:
        policy = build_delegation_policy(
            wallet_address=wallet_address,
            allowed_protocols=allowed_protocols,
            chain_name=chain,
        )
    except PolicyMappingError as exc:
        raise DelegationPolicyError(f"policy mapping failed: {exc}") from exc

    client = PrivyRestClient()
    try:
        result = client.create_policy(policy)
    except PrivyRestError as exc:
        # 秘密鍵・署名はログに出さない（PrivyRestError は status + 本文先頭のみ保持）
        logger.warning("Privy policy creation failed: status=%s", exc.status_code)
        raise DelegationPolicyError("Privy policy creation failed") from exc

    policy_id = str(result.get("id", "")).strip()
    if not policy_id:
        raise DelegationPolicyError("Privy returned no policy id")

    signer_id = get_server_signer_id()
    logger.info(
        "delegation policy created: chain=%s, policy_id=%s, wallet=%s",
        chain,
        policy_id,
        wallet_address,
    )
    return policy_id, signer_id
