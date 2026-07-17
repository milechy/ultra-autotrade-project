# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/total_assets_resolver.py

"""ユーザーの「総資産（total assets, USD）」を解決する共有ヘルパー。

`risk_limiter.check_trade_within_limits` の **% 判定の分母**（CLAUDE.md Rule 3: 単一取引 ≤ 総資産の
10% / Rule 4: 日次 ≤ 30%）に使う。両 Rule は ABSOLUTE と明記されているが、全呼び出し元が
`total_assets_usd=None` を渡しているため **実際には一度も効いていない**（2026-07-17 の Pendle
安全レビューで発覚）。本モジュールはその分母を供給する。

**`deposit_resolver.resolve_user_deposit_usd` と混同しないこと**（測るものが違う）:

  - `deposit`      = **運用に充てられる未投入の資金**（allocation or wallet USDC）。
                     最低入金ゲート（$200）の判定に使う。
  - `total_assets` = **総資産**。既に Aave に供給済みの資産を**含む**。% 上限の分母に使う。

deposit を分母に流用してはならない。定常状態のユーザーは資金の大半を Aave に供給済みで
wallet ≈ dust になり、`10% × dust` で **全 SUPPLY がブロック**される。

計算式::

    総資産 = Aave net (total_collateral_usd - total_debt_usd) + wallet USDC 残高

二重計上は起きない（`portfolio/aggregation.py` が明記するとおり、wallet 残高は Aave supply 分を
含まない）。対象 wallet は `smart_wallet_address` を優先し、無ければ `wallet_address`
（`deposit_resolver` および `proposals/router.py` の執行経路と同じ優先順）。

**戻り値は tri-state（本モジュールの肝）**:
  - ``Decimal``: 確定した総資産（USD）
  - ``None``   : **判定不能**（wallet 未設定 / RPC 失敗）

**判定不能を `Decimal("0")` にフォールバックしてはならない。** `aave/rebalance_service.py` は
取得失敗時に `total_usd = Decimal("0")` としているが、あれは表示・ステータス用途。同じことを
**実行ゲートでやると RPC の瞬断がそのまま取引停止になる**（表示用の fail-open が実行経路では
fail-closed に反転する）。呼び出し側は `None` を「% 判定をスキップ」として扱い、絶対額上限
（PolicyEngine Rule 3 / `POLICY_MAX_POSITION_USD`）に委ねる。これは `check_trade_within_limits`
が元々明記している契約（"0/None は絶対額上限(PolicyEngine)に委ねる"）と一致する。

金融計算は Decimal のみ（CLAUDE.md [CRITICAL] 11）。
"""

import logging
import os
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.models import User

logger = logging.getLogger(__name__)


def resolve_user_total_assets_usd(db: Session, user_id: int) -> Optional[Decimal]:
    """ユーザーの総資産（USD）を解決する。判定不能なら None。

    Args:
        db: SQLAlchemy セッション。
        user_id: 対象ユーザー ID。

    Returns:
        総資産（USD）。wallet 未設定 / RPC 失敗など判定不能な場合は None
        （**0 にはしない**。モジュール docstring 参照）。
    """
    user = db.get(User, user_id)
    wallet = (user.smart_wallet_address or user.wallet_address) if user else None
    if not wallet:
        logger.debug("[total_assets] user=%s: wallet 未設定のため判定不能", user_id)
        return None

    aave_net = _read_aave_net_usd(wallet)
    if aave_net is None:
        return None

    from app.aave.balance import read_wallet_usdc_balance  # noqa: PLC0415

    wallet_usdc = read_wallet_usdc_balance(wallet)
    if wallet_usdc is None:
        # read_wallet_usdc_balance は失敗時に None（内部で warning 済み）。
        # 「Aave 分だけ」で確定させると分母を過小評価し不当なブロックを生むので判定不能に倒す。
        logger.debug("[total_assets] user=%s: wallet USDC 取得失敗のため判定不能", user_id)
        return None

    return aave_net + wallet_usdc


def _read_aave_net_usd(wallet: str) -> Optional[Decimal]:
    """Aave の純資産（担保 - 負債, USD）を返す。取得不能なら None。

    クライアント生成は `aave/monitor.py:get_health_factor` の形を踏襲する
    （`AAVE_CLIENT_TYPE` で dummy/web3 を分岐し、web3 は env の RPC/Pool を使う）。
    `make_aave_client` は client_type 必須のファクトリで、per-wallet の read には過剰なため使わない。

    負債が担保を上回る（清算間際）ケースは **0 にクランプ**する。負値を返すと
    `total_assets_usd > 0` のガードを抜けて % 判定がスキップされ、**最も危険な状態で上限が
    外れる**ため。0 も結果的にスキップ側に倒れるが、そこは HF floor と PolicyEngine 絶対額が
    担う（本関数の責務ではない）。
    """
    ctype = os.getenv("AAVE_CLIENT_TYPE", "dummy").strip().lower()

    try:
        if ctype == "dummy":
            from app.aave.client import DummyAaveClient  # noqa: PLC0415

            account = DummyAaveClient().get_account_data(wallet)
        elif ctype == "web3":
            rpc_url = os.getenv("AAVE_RPC_URL", "")
            pool_address = os.getenv("AAVE_POOL_ADDRESS", "")
            if not rpc_url or not pool_address:
                logger.warning(
                    "[total_assets] AAVE_RPC_URL / AAVE_POOL_ADDRESS 未設定のため判定不能"
                )
                return None

            from app.aave.client import Web3AaveClient  # noqa: PLC0415

            account = Web3AaveClient(rpc_url=rpc_url, pool_address=pool_address).get_account_data(
                wallet
            )
        else:
            logger.warning("[total_assets] 未知の AAVE_CLIENT_TYPE=%r のため判定不能", ctype)
            return None
    except Exception as exc:  # noqa: BLE001
        # RPC 失敗 / web3 未導入 / 不正アドレス。**0 にしない**（module docstring 参照）。
        logger.warning("[total_assets] Aave account data 取得失敗 wallet=%s: %s", wallet, exc)
        return None

    net = Decimal(str(account.total_collateral_usd)) - Decimal(str(account.total_debt_usd))
    return net if net > Decimal("0") else Decimal("0")
