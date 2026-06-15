# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave_v4/__init__.py
"""
Aave V4 Ethereum Hub 統合レイヤー (scaffold) — docs/55_aave_v4_ethereum_hub_integration.md

Status: DRAFT / Phase 0 scaffold のみ。
- read-only スタブ実装済み (AaveV4ClientBase / DummyAaveV4Client)
- tx 送信 / write 系メソッドは一切未実装（HUMAN-REVIEW 要承認後に Phase 3 で実装）
- main.py への配線・依存追加は Phase 1 承認後
- 既存 backend/app/aave/ (V3) は無改変
"""

from app.aave_v4.client import AaveV4ClientBase, DummyAaveV4Client
from app.aave_v4.schemas import AaveV4HubConfig, V4AccountData

__all__ = [
    "AaveV4ClientBase",
    "DummyAaveV4Client",
    "AaveV4HubConfig",
    "V4AccountData",
]
