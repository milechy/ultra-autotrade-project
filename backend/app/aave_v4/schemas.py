# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave_v4/schemas.py
"""
Aave V4 Ethereum Hub 統合レイヤー — 型定義

全金融値は Decimal 型 (CLAUDE.md Security Rule 11: float 禁止)。
依存追加・tx 実行・main.py 配線は HUMAN-REVIEW 要承認 (docs/55 §4, §5)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class AaveV4HubConfig:
    """Aave V4 Ethereum Hub への接続設定。

    hub_address と rpc_url はアドレス確定後 (Phase 1) に env 経由で供給する。
    現時点 (Phase 0 scaffold) では空文字列をデフォルトとし、
    実装クラスが NotImplementedError を raise することで未確定を明示する。

    Attributes:
        hub_address: Ethereum Hub コントラクトアドレス (EIP-55 チェックサム形式)。
                     【要確認】Base 上の V4 Hub アドレスは 2026-06 時点で未公開。
        rpc_url:     Ethereum / Base の RPC エンドポイント。env 経由で供給。
        chain_id:    接続チェーンの chain ID。
                     Ethereum Mainnet = 1、Base Mainnet = 8453。
        timeout_sec: RPC 呼び出しタイムアウト (秒)。
    """

    hub_address: str = ""
    rpc_url: str = ""
    chain_id: int = 0
    timeout_sec: int = 10


@dataclass
class V4AccountData:
    """Aave V4 アカウントデータ。

    既存 V3 の AccountData (backend/app/aave/client.py L235-241) と同形。
    V4 Hub の API 確定後にフィールドを追加・変更する場合は
    docs/55 §1「【要確認】項目」を先に更新すること。

    全フィールドは Decimal 型 (CLAUDE.md Security Rule 11: float 禁止)。

    Attributes:
        total_collateral_usd:  総担保額 (USD 建て)。
        total_debt_usd:        総負債額 (USD 建て)。
        available_borrows_usd: 追加借入可能額 (USD 建て)。
        health_factor:         ヘルスファクター。
                               ポジションなし場合は Decimal("inf")。
    """

    total_collateral_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    total_debt_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    available_borrows_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    health_factor: Decimal = field(default_factory=lambda: Decimal("0"))
