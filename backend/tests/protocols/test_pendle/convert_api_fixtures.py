# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Pendle Convert API のレスポンス形を組み立てる共通ヘルパ（テスト用）。

**この形は実 API の応答に一致させること**。2026-07-17 まで各テストが旧 SDK（`/sdk/api/v1` +
`{"data": {"tx": ..., "amountOut": ...}}`）の形を各ファイルで独自にモックしていたが、その
エンドポイントは実在せず（全チェーンで 404）、実 API は Convert API
（`/core/v2/sdk/{chainId}/convert`）で応答形も別物だった。モックが架空の契約を固定していたため、
実装が壊れていることを誰も検出できなかった。

同じ事故を繰り返さないため:
  - モック形の定義は**本ファイル 1 箇所**に集約する（各テストで手書きしない）。
  - 実 API との整合は `test_pendle_convert_api_contract.py`（live 疎通・opt-in）が担保する。

実 API の応答例（Base 8453 / USDC → PT-yoUSD / 2026-07-17 実測）::

    {
      "action": "swap",
      "requiredApprovals": [{"token": "0x8335...2913", "amount": "1000000"}],
      "routes": [{
        "tx": {"to": "0x8888888888897...F946", "data": "0xc81f847a...", "value": "0"},
        "outputs": [{"token": "0x1fec...de29", "amount": "1033059"}],
        "data": {"priceImpact": ...}
      }]
    }

注意: ``requiredApprovals`` に **spender は含まれない**（approve 先は常に route の tx.to=Router）。
"""

from __future__ import annotations

from typing import Any

#: Pendle RouterV4（本番実アドレス）。
ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"


def convert_response(
    *,
    to: str = ROUTER,
    data: str | None = "0xdeadbeef",
    action: str = "swap",
    outputs: list[dict[str, Any]] | None = None,
    required_approvals: list[dict[str, Any]] | None = None,
    include_tx: bool = True,
    include_routes: bool = True,
) -> dict[str, Any]:
    """Convert API の応答を組み立てる。

    :param to: ``routes[0].tx.to``。Router 以外にすると client は fail-closed で拒否する。
    :param data: ``routes[0].tx.data``（calldata）。None/"" で欠損ケースを再現する。
    :param outputs: ``routes[0].outputs``。未指定なら空（amount_out=0 相当）。
    :param required_approvals: ``requiredApprovals``。実 API 同様 spender は含めないこと。
    :param include_tx: False で ``tx`` キー自体を落とす（tx 欠損ケース）。
    :param include_routes: False で ``routes`` を空にする（route 欠損ケース）。
    """
    tx: dict[str, Any] = {}
    if include_tx:
        tx["to"] = to
        if data is not None:
            tx["data"] = data

    route: dict[str, Any] = {"tx": tx, "outputs": outputs or []}
    return {
        "action": action,
        "requiredApprovals": required_approvals or [],
        "routes": [route] if include_routes else [],
    }


def output(token: str, amount_wei: int) -> dict[str, Any]:
    """``routes[0].outputs`` の 1 要素。"""
    return {"token": token, "amount": str(amount_wei)}


def approval(token: str, amount_wei: int) -> dict[str, Any]:
    """``requiredApprovals`` の 1 要素（実 API 同様 spender は持たない）。"""
    return {"token": token, "amount": str(amount_wei)}
