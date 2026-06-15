# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave_v4/client.py
"""
Aave V4 Ethereum Hub 統合レイヤー — read-only スタブ

Phase 0 scaffold: シグネチャ定義のみ。tx 送信・write 系は定義しない。

設計詳細: docs/55_aave_v4_ethereum_hub_integration.md
親設計書: docs/54_aave_v4_migration_design.md

HUMAN-REVIEW 要: 以下は本ファイルに含まない
  - tx 送信 (supply / withdraw / approve)
  - 秘密鍵・RPC 読み出し (実行時取得)
  - main.py 配線 (Phase 4 で実施)
  - 依存追加 (requirements.txt は Tier S / Phase 1 承認後)
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from decimal import Decimal
from typing import Optional

from app.aave.client import AaveClientBase, AccountData
from app.aave_v4.schemas import AaveV4HubConfig, V4AccountData

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 抽象基底クラス
# --------------------------------------------------------------------------- #


class AaveV4ClientBase(AaveClientBase):
    """Aave V4 Ethereum Hub 統合クライアントの抽象基底クラス。

    既存 V3 AaveClientBase を継承し、サービス層 (aave/service.py) が
    型注釈 `AaveClientBase` のまま V4 実装に差し替え可能にする (OCP 準拠)。

    read-only API (get_health_factor / get_account_data / get_pool_utilization) のみ
    を定義する。V3 と同一シグネチャを維持することで、AAVE_PROTOCOL_VERSION=v4 に
    切り替えた際にサービス層を無改変にする設計 (docs/55 §2 / docs/54 §3.1)。

    tx 系メソッド (deposit / withdraw) は継承元 AaveClientBase の abstract として
    残るため、具象実装クラスが Phase 3 (HUMAN-REVIEW 承認後) に実装する。
    本 Phase 0 では具象実装を提供せず、DummyAaveV4Client のみをテスト用に提供する。
    """

    @abstractmethod
    def get_health_factor(self, wallet_address: str) -> Decimal:
        """ウォレットの Health Factor を取得する。

        V4 Hub での HF 取得 API は 2026-06 時点で UNVERIFIED (docs/55 §1)。
        確定後に具象クラスで実装する。

        Args:
            wallet_address: 対象ウォレットアドレス (EIP-55 チェックサム形式)。

        Returns:
            Decimal: Health Factor。ポジションなしの場合は Decimal("inf")。

        Raises:
            NotImplementedError: Phase 0 scaffold では具象実装なし。
            AaveV4ClientError: RPC / Hub API 呼び出し失敗時 (Phase 2 以降)。
        """

    @abstractmethod
    def get_account_data(self, wallet_address: str) -> AccountData:
        """アカウントデータを取得する (V3 AccountData 型で返す)。

        V4 Hub API 確定後は V4AccountData を AccountData にマッピングして返す。
        サービス層が AccountData を期待するため戻り型は V3 と同一にする。

        Args:
            wallet_address: 対象ウォレットアドレス。

        Returns:
            AccountData: V3 互換のアカウントデータ。

        Raises:
            NotImplementedError: Phase 0 scaffold では具象実装なし。
        """

    def get_pool_utilization(self, asset_symbol: str) -> Optional[Decimal]:
        """プール利用率 (0-100) を返す。

        V4 Hub でのプール利用率取得 API は UNVERIFIED (docs/55 §1)。
        Phase 2 以降に具象実装を追加するまで None を返す (fail-open)。

        Args:
            asset_symbol: 資産シンボル ("USDC", "WETH" 等)。

        Returns:
            Optional[Decimal]: 利用率 (0-100)、または None。
        """
        logger.debug(
            "AaveV4ClientBase.get_pool_utilization: V4 Hub API 未確定のため None 返却 "
            "(docs/55 §1 要確認項目)",
        )
        return None


# --------------------------------------------------------------------------- #
# テスト / ローカル開発用ダミー実装
# --------------------------------------------------------------------------- #


class DummyAaveV4Client(AaveV4ClientBase):
    """Aave V4 テスト・ローカル開発用ダミークライアント。

    実際の RPC 接続は行わない。固定 Decimal 値を返す read-only 実装。
    既存 DummyAaveClient (backend/app/aave/client.py L356-) に倣い、
    V4 向けのテスト可能インターフェースを提供する。

    tx 系メソッド (deposit / withdraw) は stub (NotImplementedError) として
    実装することで AaveClientBase の abstract contract を満たす。
    ただし本クラスは **read-only テスト専用** であり、実運用での tx 送信は行わない。

    Note:
        write 操作 / 秘密鍵取得 / RPC 接続は一切行わない。
        本クラスへの tx 系呼び出しは必ず NotImplementedError を raise する。
    """

    def __init__(self, config: Optional[AaveV4HubConfig] = None) -> None:
        """初期化。config は将来の Phase 2 実装用に受け付けるが、ダミーでは使用しない。"""
        self._config = config or AaveV4HubConfig()

    # ------------------------------------------------------------------ #
    # read-only メソッド (テスト可能な固定値実装)
    # ------------------------------------------------------------------ #

    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        """固定 Health Factor (2.5) を返す。V4 read API 確定前のスタブ値。"""
        logger.info("DummyAaveV4Client.get_health_factor called (no RPC, V4 scaffold)")
        return Decimal("2.5")

    def get_account_data(self, wallet_address: str = "") -> AccountData:
        """固定 AccountData を返す。V3 AccountData と同形。"""
        logger.info("DummyAaveV4Client.get_account_data called (no RPC, V4 scaffold)")
        return AccountData(
            total_collateral_usd=Decimal("10000"),
            total_debt_usd=Decimal("3000"),
            available_borrows_usd=Decimal("5000"),
            health_factor=Decimal("2.5"),
        )

    def get_pool_utilization(self, asset_symbol: str = "") -> Optional[Decimal]:
        """固定プール利用率 (75.0%) を返す。V4 API 確定前のスタブ値。"""
        logger.info("DummyAaveV4Client.get_pool_utilization called (no RPC, V4 scaffold)")
        return Decimal("75.0")

    def get_v4_account_data(self, wallet_address: str = "") -> V4AccountData:
        """V4AccountData スキーマで返す補助メソッド (テスト用)。"""
        logger.info("DummyAaveV4Client.get_v4_account_data called (no RPC, V4 scaffold)")
        return V4AccountData(
            total_collateral_usd=Decimal("10000"),
            total_debt_usd=Decimal("3000"),
            available_borrows_usd=Decimal("5000"),
            health_factor=Decimal("2.5"),
        )

    # ------------------------------------------------------------------ #
    # tx 系 stub — AaveClientBase abstract を満たすが呼び出し禁止
    # ------------------------------------------------------------------ #

    def deposit(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
    ) -> "dict[str, object] | str":
        """V4 supply / deposit は Phase 3 (HUMAN-REVIEW 承認後) に実装。"""
        raise NotImplementedError(
            "V4 deposit は Ethereum Hub アドレス/SDK 確定後に実装 (docs/55 §5 Phase 3)"
        )

    def withdraw(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
    ) -> "dict[str, object] | str":
        """V4 withdraw は Phase 3 (HUMAN-REVIEW 承認後) に実装。"""
        raise NotImplementedError(
            "V4 withdraw は Ethereum Hub アドレス/SDK 確定後に実装 (docs/55 §5 Phase 3)"
        )


# --------------------------------------------------------------------------- #
# 本体スタブ (具象実装 — Phase 2 以降)
# --------------------------------------------------------------------------- #


class AaveV4EthereumHubClient(AaveV4ClientBase):
    """Aave V4 Ethereum Hub との実通信クライアント (Phase 2 以降実装)。

    Phase 0 scaffold: 全メソッドが NotImplementedError を raise する。
    Phase 2 (HUMAN-REVIEW 承認後) に web3.py または @aave/client SDK 経由で実装する。
    SDK / 言語選定は docs/55 §3 の三択比較表 + 人間承認による (HUMAN-REVIEW 必須)。

    Note:
        秘密鍵・RPC URL は実装時も env 経由のみ (CLAUDE.md Security Rule 1)。
        コンストラクタでは env 読み出しを行わない (Phase 0 制約)。
    """

    def __init__(self, config: Optional[AaveV4HubConfig] = None) -> None:
        """初期化。Phase 0 では config を受け取るのみで RPC 接続は行わない。"""
        self._config = config or AaveV4HubConfig()

    def get_health_factor(self, wallet_address: str) -> Decimal:
        """V4 Hub での HF 取得。Phase 2 以降に実装予定。"""
        raise NotImplementedError("V4 read API は Ethereum Hub アドレス/SDK 確定後に実装 (docs/55)")

    def get_account_data(self, wallet_address: str) -> AccountData:
        """V4 Hub でのアカウントデータ取得。Phase 2 以降に実装予定。"""
        raise NotImplementedError("V4 read API は Ethereum Hub アドレス/SDK 確定後に実装 (docs/55)")

    def deposit(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
    ) -> "dict[str, object] | str":
        """V4 supply / deposit は Phase 3 (HUMAN-REVIEW 承認後) に実装。"""
        raise NotImplementedError(
            "V4 deposit は Ethereum Hub アドレス/SDK 確定後に実装 (docs/55 §5 Phase 3)"
        )

    def withdraw(
        self,
        asset_address: str = "",
        amount: Decimal = Decimal("0"),
        wallet_address: str = "",
        private_key: str = "",
        dry_run: bool = False,
    ) -> "dict[str, object] | str":
        """V4 withdraw は Phase 3 (HUMAN-REVIEW 承認後) に実装。"""
        raise NotImplementedError(
            "V4 withdraw は Ethereum Hub アドレス/SDK 確定後に実装 (docs/55 §5 Phase 3)"
        )
