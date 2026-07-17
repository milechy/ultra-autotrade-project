# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/pendle_scw.py
"""[Phase D / D3] Pendle BUY_PT swap を ERC-5792 calls に変換する（委譲 SCW 経路）。

RouterV4 Hosted SDK が返す swap 結果（``RouterV4SwapResult``: swap calldata + 必要な ERC20
``approvals``）を、``scw_executor.execute_calls_via_scw`` が受け取る ``[{to,value,data}]`` 形式に
変換する。``scw_executor.build_supply_calls``（Aave 版）の Pendle 相当。

- approve → swap の順を保持して batch する（SCW が 1 UserOp で実行）。
- approve calldata は web3 v7 ``Contract.encode_abi("approve", args=[spender, amount])`` で
  オフライン生成する（``app/aave/client.py`` の ``build_deposit_txs`` を踏襲・provider 不要）。
- spender は必ず SDK approvals の値を使い、swap の宛先 Router（``result.to``・SDK 側で Router
  照合済）と一致することを検証する（不一致は fail-closed）。
- approvals 欠損 / calldata 欠損 / spender 不一致は例外（空 tx・任意宛先送信の温床を断つ）。

本 module は web3 encode（純関数）のみで、Privy 送信・秘密鍵・broadcast は一切行わない。
"""

from __future__ import annotations

import logging
from typing import Any

from web3 import Web3

from app.aave.client import _ERC20_ABI_MINIMAL
from app.protocols.pendle.schemas import RouterV4SwapResult

logger = logging.getLogger(__name__)


class PendleScwCallsError(RuntimeError):
    """Pendle swap を ERC-5792 calls に変換できない（fail-closed）。"""


def _encode_approve(token: str, spender: str, amount_raw: str) -> str:
    """ERC20 ``approve(spender, amount)`` calldata をオフライン生成する（web3 v7）。"""
    w3 = Web3()  # provider 不要: encode_abi は純粋なオフライン ABI エンコード
    token_contract = w3.eth.contract(
        address=Web3.to_checksum_address(token),
        abi=_ERC20_ABI_MINIMAL,
    )
    data: str = token_contract.encode_abi(
        "approve",
        args=[Web3.to_checksum_address(spender), int(amount_raw)],
    )
    return data


def build_pendle_swap_calls(result: RouterV4SwapResult) -> list[dict[str, Any]]:
    """``RouterV4SwapResult`` を ERC-5792 calls（approve(s) → swap）に変換する。

    各 call は ``{to, value, data}`` のみ（from/nonce/gas は SCW/bundler が決める）。

    Raises:
        PendleScwCallsError: swap 失敗 / calldata・宛先欠損 / approval 情報欠損 /
            spender が swap 宛先 Router と不一致。
    """
    if not result.success:
        raise PendleScwCallsError(f"swap result not successful: {result.error or 'unknown'}")
    router_to = result.to
    if not router_to or not result.calldata:
        raise PendleScwCallsError("swap result missing to/calldata")

    router_cs = Web3.to_checksum_address(router_to)
    calls: list[dict[str, Any]] = []
    for approval in result.approvals:
        if not approval.token or not approval.spender or approval.amount is None:
            raise PendleScwCallsError(
                "approval missing token/spender/amount (SCW approve を組めない)"
            )
        # spender は必ず swap 宛先 Router と一致すること（任意コントラクトへの approve を拒否）。
        # Convert API は spender を返さないため client が「Router 照合済みの tx.to」を spender として
        # 補完する（client._extract_approvals）。よって通常ここは常に一致するが、供給元が変わっても
        # 「照合済み Router 以外へ approve しない」不変条件が破れないよう多層防御として残す。
        if Web3.to_checksum_address(approval.spender) != router_cs:
            raise PendleScwCallsError(
                f"approval spender {approval.spender} != swap router {router_to}"
            )
        calls.append(
            {
                "to": Web3.to_checksum_address(approval.token),
                "value": "0x0",
                "data": _encode_approve(approval.token, approval.spender, approval.amount),
            }
        )

    # swap 本体は最後（approve 群の後）。
    calls.append({"to": router_cs, "value": "0x0", "data": result.calldata})
    logger.info(
        "build_pendle_swap_calls: %d approve(s) + 1 swap (router=%s)",
        len(calls) - 1,
        router_cs[:10] + "...",
    )
    return calls
