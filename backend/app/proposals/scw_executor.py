# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/scw_executor.py
"""委譲(SCW)経路の実行コア（v4 Phase 2-D-C）。

ユーザーの非カストディアル Smart Wallet(SCW) を、サーバが session signer として委譲枠の
範囲で駆動する実行層。Privy `wallet_sendCalls`(ERC-5792) 1 呼び出しで approve+supply を
batch 送信する（spike probe3 で broadcast 到達を実証 = [[project_privy_signuserop_signonly]]）。
従来の custodial EOA 直署名（`MultiChainAaveService.execute_rebalance`）の置換候補。

**dormant（本番 inert）**: `execute_calls_via_scw` は `is_delegation_policy_enabled()`
（DELEGATION_PRIVY_POLICY_ENABLED + L0 signer id + Privy creds）が揃わない限り
`ScwNotEnabledError` を送出し Privy を一切叩かない。`PrivyRestClient` も creds 必須。

**未配線（意図的）**: `_execute_aave_for_proposal`（proposals/router.py）への結線は別スライス
（2-D-C.2）。理由 = Privy `send_calls` は **Privy 内部の wallet ID** を要するが、現状 users に
`privy_wallet_id` 列が無い（`privy_did`/`smart_wallet_address` のみ）。実ユーザー結線には
wallet ID 解決の配線が先に要る。本 module はその解決後に呼ばれる実行コアを提供する。

安全分担（[[policy_mapper]] の二重ガード）: 本 module は「枠内に制約された送信」の実行のみ。
HARD_STOP / risk_limiter %クランプ / Rule8（2-D-A）は **呼び出し元 router が執行直前に通す**
（本 module はそれらを再実装しない）。出金は委譲対象外＝呼び出し元が SUPPLY のみ通す。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.aave.chains import get_chain_config
from app.privy.delegation_service import is_delegation_policy_enabled
from app.privy.rest_client import PrivyRestClient, PrivyRestError

logger = logging.getLogger(__name__)


class ScwNotEnabledError(RuntimeError):
    """委譲(SCW)実行が未有効化（dormant）。"""


class ScwExecutionError(RuntimeError):
    """委譲(SCW)実行が失敗した（Privy エラー等）。"""


@dataclass(frozen=True)
class ScwExecutionResult:
    """委譲(SCW)送信の結果。"""

    tx_hash: Optional[str]
    """broadcast された tx hash（取れない場合は None・raw を参照）。"""

    status: str
    """"submitted"（送信受理）/ "unknown"（hash 不明）。"""

    raw: dict[str, Any]
    """Privy レスポンス原文（監査用・秘密は含まれない）。"""


def caip2_for_chain(chain_name: str) -> str:
    """チェーン名 → CAIP-2（``eip155:<chain_id>``）。本番 base=eip155:8453 / staging
    base_sepolia=eip155:84532。"""
    return f"eip155:{get_chain_config(chain_name).chain_id}"


def build_supply_calls(deposit_txs: dict[str, Any]) -> list[dict[str, Any]]:
    """`AaveClient.build_deposit_txs` の戻り（approve_tx / supply_tx）を ERC-5792 calls に変換。

    approve → supply の順を保持して batch する（SCW が 1 UserOp で実行）。各 call は
    ``{to, value, data}`` のみ（from/nonce/gas は SCW/bundler が決める）。
    """
    calls: list[dict[str, Any]] = []
    for key in ("approve_tx", "supply_tx"):
        tx = deposit_txs.get(key)
        if not tx:
            continue
        calls.append(
            {
                "to": tx["to"],
                "value": tx.get("value", "0x0"),
                "data": tx["data"],
            }
        )
    if not calls:
        raise ScwExecutionError("no calls built from deposit_txs (missing approve_tx/supply_tx)")
    return calls


def _extract_tx_hash(resp: dict[str, Any]) -> Optional[str]:
    """Privy wallet_sendCalls レスポンスから tx hash を best-effort で取り出す。"""
    for key in ("transaction_hash", "hash", "transactionHash"):
        val = resp.get(key)
        if isinstance(val, str) and val:
            return val
    # ネストした result.* も見る
    result = resp.get("result")
    if isinstance(result, dict):
        for key in ("transaction_hash", "hash", "transactionHash"):
            val = result.get(key)
            if isinstance(val, str) and val:
                return val
    return None


def execute_calls_via_scw(
    *,
    privy_wallet_id: str,
    chain_name: str,
    calls: list[dict[str, Any]],
    sponsor: bool = True,
    idempotency_key: Optional[str] = None,
    client: Optional[PrivyRestClient] = None,
) -> ScwExecutionResult:
    """委譲枠内の calls を SCW 経由で送信する（ERC-5792 wallet_sendCalls）。

    :param privy_wallet_id: 委譲対象 EOA の **Privy 内部 wallet ID**（アドレスではない）
    :param chain_name: 執行チェーン名（caip2 に変換）
    :param calls: ``[{to, value, data}, ...]``（`build_supply_calls` の出力）
    :param sponsor: paymaster sponsor（True=gasless）
    :param client: テスト用 DI（未指定なら env から構築）
    :raises ScwNotEnabledError: dormant（未有効化）時
    :raises ScwExecutionError: 入力不正 / Privy 送信失敗
    """
    if not is_delegation_policy_enabled():
        raise ScwNotEnabledError(
            "SCW delegated execution is not enabled "
            "(requires DELEGATION_PRIVY_POLICY_ENABLED + PRIVY_SERVER_SIGNER_ID after L0)"
        )
    if not privy_wallet_id:
        raise ScwExecutionError("privy_wallet_id is required")
    if not calls:
        raise ScwExecutionError("calls must not be empty")

    caip2 = caip2_for_chain(chain_name)
    rest = client or PrivyRestClient()
    try:
        resp = rest.send_calls(
            privy_wallet_id,
            caip2=caip2,
            calls=calls,
            sponsor=sponsor,
            idempotency_key=idempotency_key,
        )
    except PrivyRestError as exc:
        # 秘密鍵・署名はログに出さない（status のみ）
        logger.warning("SCW send_calls failed: status=%s", exc.status_code)
        raise ScwExecutionError("Privy send_calls failed") from exc

    tx_hash = _extract_tx_hash(resp)
    logger.info(
        "SCW execution submitted: chain=%s, wallet_id=%s, tx=%s",
        chain_name,
        privy_wallet_id[:6] + "...",
        tx_hash or "(pending)",
    )
    return ScwExecutionResult(
        tx_hash=tx_hash,
        status="submitted" if tx_hash else "unknown",
        raw=resp,
    )
