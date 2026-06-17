# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/userop_verify.py
"""ERC-4337 UserOperation receipt 検証 (Privy Smart Wallet AA 移行 / スライス2)。

設計: docs/privy-aa-paymaster-design.md §3 / §6.2 スライス2（hkobayashi 承認済 2026-06-17）。

現行 `_verify_on_chain_receipt`（proposals/router.py）は EOA が直接送信した tx を前提に
`receipt["from"] == 本人EOA` を検証する。ERC-4337 では実 tx の from が EntryPoint/bundler に
なるためこの検証が破綻する。本モジュールは bundler の `eth_getUserOperationReceipt` を用いて
UserOp 単位で success / sender(=本人 Smart Wallet) を検証する代替経路を提供する。

【fail-closed 維持の階層化】
- 「他人宛て tx を組ませない」主担保は build-tx 側 (verify_supply_onbehalf / verify_withdraw_to)
  の calldata 検証であり、AA 移行後も不変。
- 本 helper は「成功したか (success) / 正しい Smart Wallet が実行したか (sender)」を検証する。

【配線状況】本 helper は現時点ではどのライブ経路にも未配線（スライス3 で
`users.smart_wallet_address` 判別子を追加し submit_partner_tx から呼び出す）。単体テストで
exercise されており孤立コードではない。実 bundler との結合はスライス7 PoC の receipt 構造
確認後に行う。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional, cast

# bundler JSON-RPC メソッド名（ERC-4337 標準）。
_USEROP_RECEIPT_METHOD = "eth_getUserOperationReceipt"


class UserOpVerificationError(ValueError):
    """UserOp receipt 検証に失敗した（pending / reverted / sender 不一致 / 取得不能）。

    ValueError を継承するため、既存 submit-tx の except 経路（恒久エラー→400/422）と
    互換に扱える。
    """


def _default_rpc_call(bundler_url: str) -> Callable[[str, list[Any]], dict[str, Any]]:
    """web3.py HTTPProvider 経由で bundler の JSON-RPC を叩く呼び出し器を返す。

    `eth_getUserOperationReceipt` は標準 eth メソッドではないため
    `provider.make_request` で生 RPC を送る。
    """
    from web3 import Web3  # noqa: PLC0415
    from web3.types import RPCEndpoint  # noqa: PLC0415

    w3 = Web3(Web3.HTTPProvider(bundler_url))

    def _call(method: str, params: list[Any]) -> dict[str, Any]:
        return cast(
            "dict[str, Any]",
            w3.provider.make_request(RPCEndpoint(method), params),
        )

    return _call


def verify_userop_receipt(
    user_op_hash: str,
    expected_sender: str,
    bundler_url: str,
    *,
    poll_interval: float = 3.0,
    max_wait: float = 60.0,
    rpc_call: Optional[Callable[[str, list[Any]], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """UserOp の receipt を bundler から取得して success / sender を検証する (fail-closed)。

    検証内容:
    - receipt が pending (result=None) なら poll_interval 秒おきに max_wait 秒まで再試行
    - max_wait 経過しても pending なら UserOpVerificationError
    - result["success"] is True 必須（False/欠落 → UserOpVerificationError）
    - result["sender"].lower() == expected_sender.lower() 必須（不一致 → UserOpVerificationError）

    :param user_op_hash: bundler が返した UserOp ハッシュ (0x + 64 hex)
    :param expected_sender: 本人の Smart Wallet アドレス (users.smart_wallet_address / slice3)
    :param bundler_url: bundler JSON-RPC URL (Pimlico 等。環境分離: staging=Base Sepolia / prod=Base)
    :param rpc_call: テスト用の RPC 呼び出し器注入口（省略時は web3 HTTPProvider）
    :returns: bundler の UserOperation receipt result dict
              （success / sender / actualGasCost / receipt 等。actualGasCost は slice6 の費目源）
    :raises UserOpVerificationError: pending タイムアウト / success!=true / sender 不一致 / RPC error
    """
    if rpc_call is None:
        rpc_call = _default_rpc_call(bundler_url)

    elapsed = 0.0
    result: Optional[dict[str, Any]] = None
    while True:
        resp = rpc_call(_USEROP_RECEIPT_METHOD, [user_op_hash])
        if resp.get("error"):
            # bundler が明示エラーを返した場合は再試行せず fail-closed。
            raise UserOpVerificationError(
                f"bundler error for userOp {user_op_hash[:12]}...: {resp['error']}"
            )
        result = resp.get("result")
        if result is not None:
            break
        if elapsed >= max_wait:
            break
        time.sleep(poll_interval)
        elapsed += poll_interval

    if result is None:
        raise UserOpVerificationError(
            f"userOp {user_op_hash[:12]}... は {max_wait:.0f}秒経過後も pending です。"
            "しばらく待ってから再試行してください。"
        )

    if result.get("success") is not True:
        raise UserOpVerificationError(
            f"userOp {user_op_hash[:12]}... は失敗 (success={result.get('success')!r}) です。"
        )

    actual_sender = str(result.get("sender") or "")
    if actual_sender.lower() != expected_sender.lower():
        raise UserOpVerificationError(
            f"userOp sender 不一致: expected={expected_sender[:6]}...{expected_sender[-4:]} "
            f"actual={actual_sender[:6] if actual_sender else '(none)'}"
        )

    return cast("dict[str, Any]", result)
