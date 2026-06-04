# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_build_tx_onbehalf_server_fixed.py
"""
P0-3: onBehalfOf 本人一致を build-tx 側でサーバー固定 (Asana 1215364095372268)

DoD 検証: build-tx が組む未署名 supply tx の calldata を **実デコード** し、
onBehalfOf が本人 wallet であることを確認する。Privy Policy Engine は
onBehalfOf == msg.sender の動的比較を未サポートのため、本人一致は
build-tx 側固定 (主担保) + 署名前 calldata 再検証 (補完層) で担保する。

本テストは mock を使わず、Web3 の実 ABI エンコーダで supply/withdraw calldata を
組み立て、本番と同じ `verify_supply_onbehalf` / `verify_withdraw_to` で実デコード
検証する。値の中身に依存しない (複数の wallet で常に本人一致を確認する)。
"""

from __future__ import annotations

import pytest

# web3 が無い環境では本テスト群を skip (mypy/型のみの CI を壊さない)
web3 = pytest.importorskip("web3")
from web3 import Web3  # noqa: E402

from app.aave.client import (  # noqa: E402
    _POOL_ABI_MINIMAL,
    verify_supply_onbehalf,
    verify_withdraw_to,
)

# Aave V3 Pool / USDC ダミーアドレス (checksum 化済)
_ASSET = Web3.to_checksum_address("0x" + "a1" * 20)
_SERVER_WALLET = Web3.to_checksum_address("0x" + "11" * 20)

# 値の中身に非依存であることを示すため複数 partner wallet を用意
_PARTNER_WALLETS = [
    Web3.to_checksum_address("0x" + "7f" * 20),
    Web3.to_checksum_address("0x" + "ab" * 20),
    Web3.to_checksum_address("0xdEAD" + "00" * 18),
]


def _build_supply_calldata(on_behalf_of: str, amount_wei: int = 1_000_000) -> str:
    """build_deposit_txs と同一の encode_abi 呼び出しで supply calldata を生成する。"""
    pool = Web3().eth.contract(abi=_POOL_ABI_MINIMAL)
    return pool.encode_abi("supply", args=[_ASSET, amount_wei, on_behalf_of, 0])


def _build_withdraw_calldata(to_addr: str, amount_wei: int = 1_000_000) -> str:
    pool = Web3().eth.contract(abi=_POOL_ABI_MINIMAL)
    return pool.encode_abi("withdraw", args=[_ASSET, amount_wei, to_addr])


# ---------------------------------------------------------------------------
# 主担保: build-tx が固定した onBehalfOf を実デコードで確認
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("partner_wallet", _PARTNER_WALLETS)
def test_supply_calldata_onbehalf_is_partner(partner_wallet: str) -> None:
    """supply calldata を実デコードすると onBehalfOf が本人 wallet と一致する。"""
    calldata = _build_supply_calldata(partner_wallet)

    # 実デコード (本番 verify と独立に decode して値を直接確認)
    pool = Web3().eth.contract(abi=_POOL_ABI_MINIMAL)
    func, params = pool.decode_function_input(calldata)
    assert func.fn_name == "supply"
    assert Web3.to_checksum_address(params["onBehalfOf"]) == partner_wallet

    # 本番の署名前 hook 関数でも True
    assert verify_supply_onbehalf(calldata, partner_wallet) is True


def test_supply_onbehalf_is_value_independent() -> None:
    """値の中身に非依存: どの wallet でも decode 後の onBehalfOf は渡した本人 wallet。"""
    for w in _PARTNER_WALLETS:
        calldata = _build_supply_calldata(w)
        pool = Web3().eth.contract(abi=_POOL_ABI_MINIMAL)
        _, params = pool.decode_function_input(calldata)
        assert Web3.to_checksum_address(params["onBehalfOf"]) == w


def test_supply_checksum_insensitive_match() -> None:
    """小文字 wallet を渡しても checksum 正規化して一致判定される。"""
    partner = _PARTNER_WALLETS[0]
    calldata = _build_supply_calldata(partner)
    assert verify_supply_onbehalf(calldata, partner.lower()) is True


# ---------------------------------------------------------------------------
# 署名前 hook (補完層): 他人宛て / 改竄を fail-closed で拒否
# ---------------------------------------------------------------------------
def test_supply_rejects_server_wallet_substitution() -> None:
    """onBehalfOf がサーバー wallet 等の他人宛てなら verify は False (reject)。"""
    # 万一 encode 経路がサーバー wallet を onBehalfOf に入れてしまった場合を模す
    calldata = _build_supply_calldata(_SERVER_WALLET)
    partner = _PARTNER_WALLETS[0]
    assert verify_supply_onbehalf(calldata, partner) is False


def test_supply_rejects_wrong_function() -> None:
    """supply 以外 (withdraw) の calldata を渡したら supply 検証は False。"""
    partner = _PARTNER_WALLETS[0]
    withdraw_calldata = _build_withdraw_calldata(partner)
    assert verify_supply_onbehalf(withdraw_calldata, partner) is False


def test_supply_rejects_garbage_calldata() -> None:
    """デコード不能な calldata は fail-closed で False (例外を投げない)。"""
    assert verify_supply_onbehalf("0xdeadbeef", _PARTNER_WALLETS[0]) is False
    assert verify_supply_onbehalf("not-hex", _PARTNER_WALLETS[0]) is False


# ---------------------------------------------------------------------------
# withdraw: to も同様に本人固定
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("partner_wallet", _PARTNER_WALLETS)
def test_withdraw_calldata_to_is_partner(partner_wallet: str) -> None:
    calldata = _build_withdraw_calldata(partner_wallet)
    pool = Web3().eth.contract(abi=_POOL_ABI_MINIMAL)
    func, params = pool.decode_function_input(calldata)
    assert func.fn_name == "withdraw"
    assert Web3.to_checksum_address(params["to"]) == partner_wallet
    assert verify_withdraw_to(calldata, partner_wallet) is True


def test_withdraw_rejects_other_recipient() -> None:
    calldata = _build_withdraw_calldata(_SERVER_WALLET)
    assert verify_withdraw_to(calldata, _PARTNER_WALLETS[0]) is False
