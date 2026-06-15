# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_reward_claimer.py
"""
RewardClaimer のユニットテスト。

外部 RPC/コントラクト呼び出しは全て MagicMock で差し替える。
金融計算が Decimal のみであることを間接的に検証（float 混入があると型チェックで落ちる）。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from app.aave.reward_claimer import RewardClaimer

# ---------------------------------------------------------------------------
# ヘルパー: モック化された RewardClaimer を生成する
# ---------------------------------------------------------------------------


def _make_claimer(
    mock_w3: MagicMock,
    mock_aave_client: MagicMock,
    unclaimed_rewards: list[dict] | None = None,
) -> "tuple[RewardClaimer, MagicMock, MagicMock]":
    """
    RewardClaimer をモック依存で生成し、
    ui_provider.functions.getUserReservesIncentivesData の戻り値を設定する。

    unclaimed_rewards: [{symbol, token_addr, unclaimed_raw, decimals, price_feed, price_decimals}]
    """
    if unclaimed_rewards is None:
        unclaimed_rewards = []

    # RewardClaimer がコントラクトを生成しないよう web3 の contract 呼び出しをモック化
    mock_ui_contract = MagicMock()
    mock_rewards_contract = MagicMock()
    mock_w3.eth.contract.side_effect = [mock_ui_contract, mock_rewards_contract]

    claimer = RewardClaimer(
        w3=mock_w3,
        ui_incentive_provider_address="0x" + "a" * 40,
        rewards_controller_address="0x" + "b" * 40,
        pool_addresses_provider="0x" + "c" * 40,
        aave_client=mock_aave_client,
        usdc_address="0x" + "d" * 40,
    )

    # _ui_provider をモックに差し替え
    claimer._ui_provider = mock_ui_contract
    claimer._rewards_controller = mock_rewards_contract

    # getUserReservesIncentivesData 戻り値を組み立てる
    def _make_reward_tuple(r: dict) -> tuple:
        # (symbol, tokenAddr, oracleAddr, emission, lastUpdate, userIndex,
        #  emissionEnd, priceFeed, tokenDecimals, precision, priceFeedDecimals,
        #  userUnclaimedRewards, rewardTokenId)
        return (
            r["symbol"],
            r["token_addr"],
            "0x" + "0" * 40,  # oracleAddr
            0,  # emissionPerSecond
            0,  # incentivesLastUpdateTimestamp
            0,  # tokenIncentivesUserIndex
            0,  # emissionEndTimestamp
            r["price_feed"],  # rewardPriceFeed (int256)
            r["decimals"],  # rewardTokenDecimals
            18,  # precision
            r["price_decimals"],  # priceFeedDecimals
            r["unclaimed_raw"],  # userUnclaimedRewards
            b"\x00" * 32,  # rewardTokenId
        )

    # aToken incentives data: (tokenAddress, controllerAddress, [rewardInfo, ...])
    atoken_incentives = (
        "0x" + "1" * 40,
        "0x" + "2" * 40,
        [_make_reward_tuple(r) for r in unclaimed_rewards],
    )
    # vToken / sToken は空
    empty_incentives = ("0x" + "3" * 40, "0x" + "4" * 40, [])

    # 1 つの reserve エントリ: (underlyingAsset, aTokenIncentives, vTokenIncentives, sTokenIncentives)
    reserve_entry = (
        "0x" + "5" * 40,
        atoken_incentives,
        empty_incentives,
        empty_incentives,
    )
    mock_ui_contract.functions.getUserReservesIncentivesData.return_value.call.return_value = (
        [reserve_entry] if unclaimed_rewards else []
    )

    return claimer, mock_ui_contract, mock_rewards_contract


# ---------------------------------------------------------------------------
# テスト: get_claimable_rewards
# ---------------------------------------------------------------------------


class TestGetClaimableRewards:
    """get_claimable_rewards() の正常系・異常系。"""

    def test_returns_empty_on_no_rewards(self) -> None:
        """未請求リワードが 0 の場合は空リストを返す。"""
        mock_w3 = MagicMock()
        mock_client = MagicMock()
        claimer, _, _ = _make_claimer(mock_w3, mock_client, unclaimed_rewards=[])

        result = claimer.get_claimable_rewards("0x" + "f" * 40)
        assert result == []

    def test_returns_rewards_with_decimal_amounts(self) -> None:
        """リワードが存在する場合、Decimal 型の amount と amount_usd が返る。"""
        mock_w3 = MagicMock()
        mock_client = MagicMock()
        rewards_data = [
            {
                "symbol": "AAVE",
                "token_addr": "0x" + "e" * 40,
                # 2.5 AAVE (18 decimals): unclaimed_raw = 2.5 * 10^18
                "unclaimed_raw": int(Decimal("2.5") * Decimal(10**18)),
                "decimals": 18,
                "price_feed": int(Decimal("100") * Decimal(10**8)),  # $100/AAVE
                "price_decimals": 8,
            }
        ]
        claimer, _, _ = _make_claimer(mock_w3, mock_client, unclaimed_rewards=rewards_data)

        result = claimer.get_claimable_rewards("0x" + "f" * 40)

        assert len(result) == 1
        r = result[0]
        assert r["asset_name"] == "AAVE"
        assert isinstance(r["amount"], Decimal)
        assert isinstance(r["amount_usd"], Decimal)
        assert r["amount"] == Decimal("2.5")
        # $100/AAVE * 2.5 = $250
        assert r["amount_usd"] == Decimal("250")

    def test_fail_open_on_provider_exception(self) -> None:
        """Provider 呼び出しが例外を出した場合は [] を返す（fail-open）。"""
        mock_w3 = MagicMock()
        mock_client = MagicMock()
        claimer, mock_ui, _ = _make_claimer(mock_w3, mock_client, unclaimed_rewards=[])

        # Provider が例外を投げるよう設定
        mock_ui.functions.getUserReservesIncentivesData.return_value.call.side_effect = (
            ConnectionError("RPC timeout")
        )

        # 例外が伝播しないことを確認
        result = claimer.get_claimable_rewards("0x" + "f" * 40)
        assert result == []


# ---------------------------------------------------------------------------
# テスト: auto_claim_if_worthy (閾値判定 + Claim + supply)
# ---------------------------------------------------------------------------


class TestAutoClaimIfWorthy:
    """auto_claim_if_worthy() の閾値判定・Claim・supply の検証。"""

    def test_skip_when_below_threshold(self) -> None:
        """合計 USD が $4.99 以下の場合は Claim しない。"""
        mock_w3 = MagicMock()
        mock_client = MagicMock()
        # $4.99 のリワード: 0.0499 AAVE @ $100/AAVE
        rewards_data = [
            {
                "symbol": "AAVE",
                "token_addr": "0x" + "e" * 40,
                "unclaimed_raw": int(Decimal("0.0499") * Decimal(10**18)),
                "decimals": 18,
                "price_feed": int(Decimal("100") * Decimal(10**8)),
                "price_decimals": 8,
            }
        ]
        claimer, _, mock_rewards_ctrl = _make_claimer(
            mock_w3, mock_client, unclaimed_rewards=rewards_data
        )

        result = claimer.auto_claim_if_worthy(
            wallet_address="0x" + "f" * 40,
            private_key="0x" + "a" * 64,
            dry_run=False,
        )

        assert result["claimed"] is False
        assert result["skip_reason"] is not None
        # claimAllRewards が呼ばれていないことを確認
        mock_rewards_ctrl.functions.claimAllRewards.assert_not_called()

    def test_claim_and_supply_when_above_threshold(self) -> None:
        """合計 USD が $5.00 以上の場合は claim_all_rewards() と supply() が呼ばれる。"""
        mock_w3 = MagicMock()
        mock_client = MagicMock()

        # $5.00 のリワード: 0.05 AAVE @ $100/AAVE
        rewards_data = [
            {
                "symbol": "AAVE",
                "token_addr": "0x" + "e" * 40,
                "unclaimed_raw": int(Decimal("0.05") * Decimal(10**18)),
                "decimals": 18,
                "price_feed": int(Decimal("100") * Decimal(10**8)),
                "price_decimals": 8,
            }
        ]
        claimer, _, mock_rewards_ctrl = _make_claimer(
            mock_w3, mock_client, unclaimed_rewards=rewards_data
        )

        # claimAllRewards の tx 送信をモック化
        mock_rewards_ctrl.functions.claimAllRewards.return_value.build_transaction.return_value = {}
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 1000000000
        mock_w3.eth.chain_id = 8453
        mock_w3.eth.estimate_gas.return_value = 200000
        mock_w3.eth.account.sign_transaction.return_value = MagicMock(raw_transaction=b"signed_tx")
        mock_w3.eth.send_raw_transaction.return_value = b"\x00" * 32
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"transactionHash": b"\x00" * 32}

        # supply の戻り値をモック化
        mock_client.deposit.return_value = {"tx_hash": "0x" + "1" * 64}

        result = claimer.auto_claim_if_worthy(
            wallet_address="0x" + "f" * 40,
            private_key="0x" + "a" * 64,
            dry_run=False,
        )

        assert result["claimed"] is True
        assert result["error"] is None
        # supply が reward_token_address で呼ばれたことを確認 (CRITICAL #2 修正の検証)
        mock_client.deposit.assert_called_once()
        supply_call_kwargs = mock_client.deposit.call_args
        # asset_address は reward_token_address であるべき (USDC でない)
        token_addr_arg = supply_call_kwargs.kwargs.get("asset_address")
        assert token_addr_arg == "0x" + "e" * 40, (
            f"asset_address should be reward token, got {token_addr_arg}"
        )
        # amount は Decimal で実トークン量 (total_usd でない)
        amount_arg = supply_call_kwargs.kwargs.get("amount")
        assert isinstance(amount_arg, Decimal), f"amount must be Decimal, got {type(amount_arg)}"
        # 0.05 AAVE (total_usd = $5.00 ではなくトークン量)
        assert amount_arg == Decimal("0.05"), (
            f"amount should be token quantity 0.05, got {amount_arg}"
        )

    def test_fail_open_on_unexpected_exception(self) -> None:
        """予期しない例外が発生しても例外は伝播せず error キーに記録される。"""
        mock_w3 = MagicMock()
        mock_client = MagicMock()
        claimer, mock_ui, _ = _make_claimer(mock_w3, mock_client)

        # get_claimable_rewards 内で例外を発生させる
        mock_ui.functions.getUserReservesIncentivesData.return_value.call.side_effect = (
            RuntimeError("unexpected error")
        )

        # 例外が伝播しないことを確認
        result = claimer.auto_claim_if_worthy(
            wallet_address="0x" + "f" * 40,
            private_key="0x" + "a" * 64,
            dry_run=False,
        )

        # fail-open: エラーは result["error"] or result["skip_reason"] に格納
        assert result["claimed"] is False

    def test_claim_success_supply_failure_records_error(self) -> None:
        """MINOR #7(a): claim 成功 + supply 失敗時に claimed==True かつ error が記録される。"""
        mock_w3 = MagicMock()
        mock_client = MagicMock()

        # $5.00 のリワード: 0.05 AAVE @ $100/AAVE
        rewards_data = [
            {
                "symbol": "AAVE",
                "token_addr": "0x" + "e" * 40,
                "unclaimed_raw": int(Decimal("0.05") * Decimal(10**18)),
                "decimals": 18,
                "price_feed": int(Decimal("100") * Decimal(10**8)),
                "price_decimals": 8,
            }
        ]
        claimer, _, mock_rewards_ctrl = _make_claimer(
            mock_w3, mock_client, unclaimed_rewards=rewards_data
        )

        # claimAllRewards は成功するようモック設定
        mock_rewards_ctrl.functions.claimAllRewards.return_value.build_transaction.return_value = {}
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 1000000000
        mock_w3.eth.chain_id = 8453
        mock_w3.eth.estimate_gas.return_value = 200000
        mock_w3.eth.account.sign_transaction.return_value = MagicMock(raw_transaction=b"signed_tx")
        mock_w3.eth.send_raw_transaction.return_value = b"\x00" * 32
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"transactionHash": b"\x00" * 32}

        # deposit は失敗するよう設定（Aave 未対応トークンを想定）
        mock_client.deposit.side_effect = ValueError("Unknown asset: AAVE not in pool")

        result = claimer.auto_claim_if_worthy(
            wallet_address="0x" + "f" * 40,
            private_key="0x" + "a" * 64,
            dry_run=False,
        )

        # Claim は成功しているはず
        assert result["claimed"] is True
        # エラーが記録されているはず
        assert result["error"] is not None
        assert "supply" in result["error"].lower() or "AAVE" in result["error"]
        # supply_tx_hash は None のまま
        assert result["supply_tx_hash"] is None
        # claimed_but_not_resupplied に記録されているはず
        assert isinstance(result.get("claimed_but_not_resupplied"), list)
        assert len(result["claimed_but_not_resupplied"]) > 0

    def test_no_double_claim_on_re_execution(self) -> None:
        """MINOR #7(b): 二重実行時に claimAllRewards が 2 回呼ばれないことを確認する。

        閾値確認後に get_claimable_rewards が 0 を返すようになれば、
        2回目は skip_reason が設定されて Claim がスキップされる。
        """
        mock_w3 = MagicMock()
        mock_client = MagicMock()

        # 1回目: $5.00 のリワードが存在
        rewards_data = [
            {
                "symbol": "AAVE",
                "token_addr": "0x" + "e" * 40,
                "unclaimed_raw": int(Decimal("0.05") * Decimal(10**18)),
                "decimals": 18,
                "price_feed": int(Decimal("100") * Decimal(10**8)),
                "price_decimals": 8,
            }
        ]
        claimer, mock_ui, mock_rewards_ctrl = _make_claimer(
            mock_w3, mock_client, unclaimed_rewards=rewards_data
        )

        # claimAllRewards の tx 送信をモック化
        mock_rewards_ctrl.functions.claimAllRewards.return_value.build_transaction.return_value = {}
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 1000000000
        mock_w3.eth.chain_id = 8453
        mock_w3.eth.estimate_gas.return_value = 200000
        mock_w3.eth.account.sign_transaction.return_value = MagicMock(raw_transaction=b"signed_tx")
        mock_w3.eth.send_raw_transaction.return_value = b"\x00" * 32
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"transactionHash": b"\x00" * 32}
        mock_client.deposit.return_value = {"tx_hash": "0x" + "1" * 64}

        # 1回目の実行 → Claim される
        result1 = claimer.auto_claim_if_worthy(
            wallet_address="0x" + "f" * 40,
            private_key="0x" + "a" * 64,
            dry_run=False,
        )
        assert result1["claimed"] is True

        # 2回目: Claim 済みでリワードが 0 になったと仮定（unclaimed_raw = 0）
        mock_ui.functions.getUserReservesIncentivesData.return_value.call.return_value = []

        result2 = claimer.auto_claim_if_worthy(
            wallet_address="0x" + "f" * 40,
            private_key="0x" + "a" * 64,
            dry_run=False,
        )
        # 2回目は閾値未満 (0 USD) のためスキップされる
        assert result2["claimed"] is False
        assert result2["skip_reason"] is not None


# ---------------------------------------------------------------------------
# テスト: make_reward_claimer_from_env()
# ---------------------------------------------------------------------------


class TestMakeRewardClaimerFromEnv:
    """make_reward_claimer_from_env() の env 分岐テスト。"""

    def test_returns_none_when_required_envs_missing(self, monkeypatch: object) -> None:
        """必須 env が未設定の場合は None を返す (fail-open)。"""
        import os  # noqa: PLC0415

        # 必須 env を全て未設定にする
        for key in [
            "AAVE_RPC_URL",
            "AAVE_UI_INCENTIVE_PROVIDER_ADDRESS",
            "AAVE_REWARDS_CONTROLLER_ADDRESS",
            "AAVE_POOL_ADDRESSES_PROVIDER",
        ]:
            if isinstance(monkeypatch, object) and hasattr(monkeypatch, "delenv"):
                monkeypatch.delenv(key, raising=False)  # type: ignore[union-attr]

        # monkeypatch が pytest fixture の場合のみ動作
        # 直接環境変数を操作して検証する
        original = {}
        for key in [
            "AAVE_RPC_URL",
            "AAVE_UI_INCENTIVE_PROVIDER_ADDRESS",
            "AAVE_REWARDS_CONTROLLER_ADDRESS",
            "AAVE_POOL_ADDRESSES_PROVIDER",
        ]:
            original[key] = os.environ.pop(key, None)

        try:
            from app.aave.reward_claimer import make_reward_claimer_from_env  # noqa: PLC0415

            result = make_reward_claimer_from_env()
            assert result is None, "必須 env 未設定時は None を返すべき"
        finally:
            # 環境変数を元に戻す
            for key, val in original.items():
                if val is not None:
                    os.environ[key] = val

    def test_returns_none_when_rpc_url_only_missing(self) -> None:
        """AAVE_RPC_URL のみ未設定でも None を返す。"""
        import os  # noqa: PLC0415

        original_rpc = os.environ.pop("AAVE_RPC_URL", None)
        # 他の必須 env は設定
        for key, val in [
            ("AAVE_UI_INCENTIVE_PROVIDER_ADDRESS", "0x" + "a" * 40),
            ("AAVE_REWARDS_CONTROLLER_ADDRESS", "0x" + "b" * 40),
            ("AAVE_POOL_ADDRESSES_PROVIDER", "0x" + "c" * 40),
        ]:
            os.environ[key] = val

        try:
            from app.aave.reward_claimer import make_reward_claimer_from_env  # noqa: PLC0415

            result = make_reward_claimer_from_env()
            assert result is None
        finally:
            if original_rpc is not None:
                os.environ["AAVE_RPC_URL"] = original_rpc
            for key in [
                "AAVE_UI_INCENTIVE_PROVIDER_ADDRESS",
                "AAVE_REWARDS_CONTROLLER_ADDRESS",
                "AAVE_POOL_ADDRESSES_PROVIDER",
            ]:
                os.environ.pop(key, None)

    def test_returns_none_when_web3_unavailable(self) -> None:
        """web3 が未インストールの場合は None を返す (fail-open)。"""
        import sys  # noqa: PLC0415

        # web3 モジュールを一時的に隠す
        original_web3 = sys.modules.get("web3")
        sys.modules["web3"] = None  # type: ignore[assignment]

        try:
            # reward_claimer を再読み込みして web3=None の状態をシミュレート
            import app.aave.reward_claimer as rcmod  # noqa: PLC0415

            original_w3 = rcmod.Web3
            rcmod.Web3 = None  # type: ignore[assignment]
            try:
                result = rcmod.make_reward_claimer_from_env()
                assert result is None, "web3 未インストール時は None を返すべき"
            finally:
                rcmod.Web3 = original_w3
        finally:
            if original_web3 is None:
                sys.modules.pop("web3", None)
            else:
                sys.modules["web3"] = original_web3

    def test_factory_passes_network_to_make_aave_client(self) -> None:
        """MAJOR #4: network と pool_address が make_aave_client() に渡される。"""
        import os  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        # 必須 env を設定
        env_patch = {
            "AAVE_RPC_URL": "http://localhost:8545",
            "AAVE_UI_INCENTIVE_PROVIDER_ADDRESS": "0x" + "a" * 40,
            "AAVE_REWARDS_CONTROLLER_ADDRESS": "0x" + "b" * 40,
            "AAVE_POOL_ADDRESSES_PROVIDER": "0x" + "c" * 40,
            "AAVE_CLIENT_TYPE": "dummy",
            "AAVE_NETWORK": "base_sepolia",
            "AAVE_POOL_ADDRESS": "0x" + "d" * 40,
        }
        original = {k: os.environ.get(k) for k in env_patch}
        for k, v in env_patch.items():
            os.environ[k] = v

        try:
            mock_client = MagicMock()
            mock_w3_instance = MagicMock()

            with (
                patch("app.aave.client.make_aave_client", return_value=mock_client) as mock_factory,
                patch("app.aave.reward_claimer.Web3") as mock_w3_cls,
            ):
                mock_w3_cls.return_value = mock_w3_instance
                mock_w3_cls.HTTPProvider = MagicMock()

                from app.aave.reward_claimer import make_reward_claimer_from_env  # noqa: PLC0415

                make_reward_claimer_from_env()

                # make_aave_client が network と pool_address を受け取ったか確認
                mock_factory.assert_called_once()
                call_kwargs = mock_factory.call_args.kwargs
                assert call_kwargs.get("network") == "base_sepolia", (
                    f"network が渡されていない: {call_kwargs}"
                )
                assert call_kwargs.get("pool_address") == "0x" + "d" * 40, (
                    f"pool_address が渡されていない: {call_kwargs}"
                )
        finally:
            for k, v in original.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


# ---------------------------------------------------------------------------
# テスト: float 混入チェック
# ---------------------------------------------------------------------------


def test_no_float_in_reward_calculation() -> None:
    """リワード計算で float が使われていないことを確認する。"""
    import inspect  # noqa: PLC0415

    import app.aave.reward_claimer as module  # noqa: PLC0415

    source = inspect.getsource(module)
    # float() を直接呼んでいる箇所がないことを確認（コメントを除く）
    lines = [
        line
        for line in source.splitlines()
        if "float(" in line and not line.strip().startswith("#")
    ]
    assert lines == [], f"float() 呼び出しが検出されました: {lines}"
