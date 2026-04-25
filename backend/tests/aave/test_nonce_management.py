# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_nonce_management.py
"""deposit/withdraw の nonce 管理テスト。

背景: 2026-04-22 インシデントで approve 送信直後の supply が nonce 競合で失敗。
原因は get_transaction_count() を都度呼ぶ設計と RPC ノードの nonce 伝播遅延。

修正: 同一フロー内では _NonceTracker が一度だけ "pending" nonce を取得し、
      peek/advance で連続 tx に sequential な nonce を明示指定する。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.aave.client import AaveClientError, Web3AaveClient, _NonceTracker


class TestNonceTracker:
    """_NonceTracker の基本動作。"""

    def test_initializes_with_pending_nonce(self) -> None:
        """初期化時に get_transaction_count(wallet, 'pending') が呼ばれる。"""
        w3 = MagicMock()
        w3.eth.get_transaction_count.return_value = 42
        wallet = "0x" + "a" * 40

        tracker = _NonceTracker(w3, wallet)

        w3.eth.get_transaction_count.assert_called_once_with(wallet, "pending")
        assert tracker.peek() == 42
        assert tracker.start == 42
        assert tracker.consumed == 0

    def test_peek_does_not_consume(self) -> None:
        """peek() を複数回呼んでも nonce は進まない。"""
        w3 = MagicMock()
        w3.eth.get_transaction_count.return_value = 10
        tracker = _NonceTracker(w3, "0x" + "b" * 40)

        assert tracker.peek() == 10
        assert tracker.peek() == 10
        assert tracker.peek() == 10
        assert tracker.consumed == 0

    def test_advance_increments(self) -> None:
        """advance() で +1 ずつ進む。"""
        w3 = MagicMock()
        w3.eth.get_transaction_count.return_value = 7
        tracker = _NonceTracker(w3, "0x" + "c" * 40)

        assert tracker.peek() == 7
        tracker.advance()
        assert tracker.peek() == 8
        assert tracker.consumed == 1
        tracker.advance()
        assert tracker.peek() == 9
        assert tracker.consumed == 2

    def test_only_one_rpc_call_across_full_flow(self) -> None:
        """3 連続 tx で get_transaction_count の RPC 呼び出しは 1 回のみ。"""
        w3 = MagicMock()
        w3.eth.get_transaction_count.return_value = 5
        tracker = _NonceTracker(w3, "0x" + "d" * 40)

        _ = tracker.peek()
        tracker.advance()
        _ = tracker.peek()
        tracker.advance()
        _ = tracker.peek()
        tracker.advance()

        assert w3.eth.get_transaction_count.call_count == 1


def _setup_mocked_web3(mock_web3_cls: MagicMock, start_nonce: int = 7) -> tuple:
    """Web3AaveClient 用の mock Web3 を組み立てる共通ヘルパー。

    戻り値: (mock_w3, mock_token, pool_mock) — テスト側から挙動を差し替える用。
    """
    mock_w3 = MagicMock()
    mock_w3.is_connected.return_value = True
    mock_web3_cls.return_value = mock_w3
    mock_web3_cls.HTTPProvider = MagicMock()
    mock_web3_cls.to_checksum_address = lambda x: x

    # ERC-20 token mock
    mock_token = MagicMock()
    mock_token.functions.decimals.return_value.call.return_value = 6  # USDC
    mock_token.functions.approve.return_value.build_transaction.return_value = {
        "mock": "approve_tx"
    }

    # Aave Pool mock
    pool_mock = MagicMock()
    pool_mock.address = "0xPoolAddress"
    pool_mock.functions.supply.return_value.build_transaction.return_value = {"mock": "supply_tx"}

    # __init__ creates pool contract; deposit creates token contract
    mock_w3.eth.contract.side_effect = [pool_mock, mock_token]

    # "pending" 付きで呼ばれた場合だけ start_nonce を返す。それ以外の呼び方 (過去の
    # バグ経路) で呼ばれたら明示的にエラーにして、実装が tracker を経由しているか検証。
    def _get_tx_count(addr: str, block: str = "latest") -> int:
        assert block == "pending", (
            f"get_transaction_count は必ず 'pending' ブロックで呼び出すこと (got block={block!r})"
        )
        return start_nonce

    mock_w3.eth.get_transaction_count.side_effect = _get_tx_count
    mock_w3.eth.gas_price = 20_000_000_000

    signed_mock = MagicMock()
    signed_mock.raw_transaction = b"signed"
    mock_w3.eth.account.sign_transaction.return_value = signed_mock

    mock_receipt = MagicMock()
    mock_receipt.transactionHash = b"\xab" * 32
    mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

    return mock_w3, mock_token, pool_mock


def _build_client(mock_w3: MagicMock, mock_token: MagicMock) -> Web3AaveClient:
    client = Web3AaveClient(rpc_url="https://mock-rpc.example.com")
    # deposit/withdraw 経由の eth.contract() は token を返すようにする
    mock_w3.eth.contract.side_effect = None
    mock_w3.eth.contract.return_value = mock_token

    mock_account = MagicMock()
    mock_account.address = "0xabc0000000000def"
    mock_account.key = b"\xab" * 32
    client.account = mock_account  # type: ignore[attr-defined]
    return client


@patch("app.aave.client.Web3")
def test_approve_and_supply_receive_sequential_nonces(mock_web3_cls: MagicMock) -> None:
    """approve→supply の連続 tx で nonce が start, start+1 で渡ることを検証。"""
    mock_w3, mock_token, pool_mock = _setup_mocked_web3(mock_web3_cls, start_nonce=7)
    mock_w3.eth.send_raw_transaction.side_effect = [b"\xaa" * 32, b"\xbb" * 32]

    client = _build_client(mock_w3, mock_token)

    client.deposit(
        asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
        amount=Decimal("10.0"),
        wallet_address="0xabc0000000000def",
        private_key="0x" + "ab" * 32,
    )

    # get_transaction_count は _NonceTracker 初期化時の 1 回だけ
    assert mock_w3.eth.get_transaction_count.call_count == 1
    mock_w3.eth.get_transaction_count.assert_called_once_with("0xabc0000000000def", "pending")

    # approve の build_transaction には nonce=7 が渡る
    approve_params = mock_token.functions.approve.return_value.build_transaction.call_args.args[0]
    assert approve_params["nonce"] == 7

    # supply の build_transaction には nonce=8 が渡る
    supply_params = pool_mock.functions.supply.return_value.build_transaction.call_args.args[0]
    assert supply_params["nonce"] == 8

    # 2 回送信
    assert mock_w3.eth.send_raw_transaction.call_count == 2


@patch("app.aave.client.Web3")
def test_approve_send_failure_aborts_supply(mock_web3_cls: MagicMock) -> None:
    """approve 送信が失敗したら supply は build も send もされない (fail-fast)。"""
    mock_w3, mock_token, pool_mock = _setup_mocked_web3(mock_web3_cls, start_nonce=7)
    # approve 送信で即失敗
    mock_w3.eth.send_raw_transaction.side_effect = Exception("approve reverted")

    client = _build_client(mock_w3, mock_token)

    with pytest.raises(Exception, match="approve reverted"):
        client.deposit(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("10.0"),
            wallet_address="0xabc0000000000def",
            private_key="0x" + "ab" * 32,
        )

    # approve は build_transaction されるが supply は一度も build されない
    assert mock_token.functions.approve.return_value.build_transaction.call_count == 1
    assert pool_mock.functions.supply.return_value.build_transaction.call_count == 0
    # send_raw_transaction は 1 回 (approve) のみ
    assert mock_w3.eth.send_raw_transaction.call_count == 1


@patch("app.aave.client.Web3")
def test_approve_supply_revoke_receive_nonces_0_1_2(mock_web3_cls: MagicMock) -> None:
    """supply 成功後に受領失敗 (revert) → revoke 実行で nonce は +0, +1, +2。"""
    mock_w3, mock_token, pool_mock = _setup_mocked_web3(mock_web3_cls, start_nonce=7)

    # approve, supply, revoke の 3 連続送信を全て成功させる
    mock_w3.eth.send_raw_transaction.side_effect = [
        b"\xaa" * 32,  # approve
        b"\xbb" * 32,  # supply (send_raw は成功)
        b"\xcc" * 32,  # revoke
    ]

    # supply の receipt 取得でエラー発生 (= supply は送信済みで nonce 消費、
    # revert により revoke パスへ入る)。approve 側の receipt は正常に返す。
    approve_receipt = MagicMock()
    approve_receipt.transactionHash = b"\xab" * 32
    revoke_receipt = MagicMock()
    revoke_receipt.transactionHash = b"\xcd" * 32
    mock_w3.eth.wait_for_transaction_receipt.side_effect = [
        approve_receipt,
        Exception("supply reverted on-chain"),
        revoke_receipt,
    ]

    client = _build_client(mock_w3, mock_token)

    with pytest.raises(AaveClientError, match="deposit 失敗"):
        client.deposit(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("10.0"),
            wallet_address="0xabc0000000000def",
            private_key="0x" + "ab" * 32,
        )

    approve_build_calls = mock_token.functions.approve.return_value.build_transaction.call_args_list
    supply_build_calls = pool_mock.functions.supply.return_value.build_transaction.call_args_list

    # approve は初回 (amount_wei > 0) + revoke (amount=0) の 2 回
    assert len(approve_build_calls) == 2
    # supply は 1 回
    assert len(supply_build_calls) == 1

    # approve (amount_wei) → nonce=7
    assert approve_build_calls[0].args[0]["nonce"] == 7
    # supply → nonce=8
    assert supply_build_calls[0].args[0]["nonce"] == 8
    # revoke (amount=0) → nonce=9 (supply が send 成功 → advance 済み)
    assert approve_build_calls[1].args[0]["nonce"] == 9

    # 3 回送信されている
    assert mock_w3.eth.send_raw_transaction.call_count == 3
    # RPC 呼び出しは初期化の 1 回のみ
    assert mock_w3.eth.get_transaction_count.call_count == 1


@patch("app.aave.client.Web3")
def test_revoke_uses_approve_plus_one_when_supply_build_fails(
    mock_web3_cls: MagicMock,
) -> None:
    """supply が send 前 (build 失敗) にこけた場合、nonce は消費されていないので
    revoke は approve_nonce + 1 を使う。"""
    mock_w3, mock_token, pool_mock = _setup_mocked_web3(mock_web3_cls, start_nonce=7)

    # supply.build_transaction を失敗させる → send は呼ばれず nonce 未消費
    pool_mock.functions.supply.return_value.build_transaction.side_effect = RuntimeError(
        "insufficient balance for gas"
    )

    # send_raw は approve と revoke の 2 回だけ成功で返す
    mock_w3.eth.send_raw_transaction.side_effect = [b"\xaa" * 32, b"\xcc" * 32]

    client = _build_client(mock_w3, mock_token)

    with pytest.raises(AaveClientError, match="deposit 失敗"):
        client.deposit(
            asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
            amount=Decimal("10.0"),
            wallet_address="0xabc0000000000def",
            private_key="0x" + "ab" * 32,
        )

    approve_build_calls = mock_token.functions.approve.return_value.build_transaction.call_args_list
    # approve は初回 + revoke の 2 回 build
    assert len(approve_build_calls) == 2
    # approve (amount_wei) → nonce=7
    assert approve_build_calls[0].args[0]["nonce"] == 7
    # revoke (amount=0) → nonce=8 (supply は send されていないので advance されない)
    assert approve_build_calls[1].args[0]["nonce"] == 8
    # send_raw は approve + revoke の 2 回
    assert mock_w3.eth.send_raw_transaction.call_count == 2


@patch("app.aave.client.Web3")
def test_withdraw_uses_pending_nonce(mock_web3_cls: MagicMock) -> None:
    """withdraw も 'pending' nonce を使う (mempool-aware)。"""
    mock_w3, mock_token, pool_mock = _setup_mocked_web3(mock_web3_cls, start_nonce=11)
    # HF = 2.5 (safe) で withdraw を許可
    hf_raw = int(Decimal("2.5") * Decimal(10**18))
    pool_mock.functions.getUserAccountData.return_value.call.return_value = (
        0,
        0,
        0,
        0,
        0,
        hf_raw,
    )
    pool_mock.functions.withdraw.return_value.build_transaction.return_value = {
        "mock": "withdraw_tx"
    }
    mock_w3.eth.send_raw_transaction.return_value = b"\xdd" * 32

    client = _build_client(mock_w3, mock_token)

    client.withdraw(
        asset_address="0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8",
        amount=Decimal("5.0"),
        wallet_address="0xabc0000000000def",
        private_key="0x" + "ab" * 32,
    )

    withdraw_params = pool_mock.functions.withdraw.return_value.build_transaction.call_args.args[0]
    assert withdraw_params["nonce"] == 11
    # 必ず 'pending' で呼ばれている (side_effect の assert で検証済み)
    mock_w3.eth.get_transaction_count.assert_called_with("0xabc0000000000def", "pending")
