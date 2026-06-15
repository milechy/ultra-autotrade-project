# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/emode_optimizer.py
"""
Aave V3.6 Liquid eMode 自動最適化ロジック。

担保資産の構成から最適な eMode カテゴリを推奨し、
切替による LTV 改善率（Decimal）を計算する。

Security Rules:
- 金融計算は Decimal のみ（float 禁止）
- setUserEMode は write 操作のため HUMAN-REVIEW-REQUIRED / admin RBAC 必須
"""

from __future__ import annotations

import logging
from decimal import Decimal

from .schemas import EModeInfo, EModeRecommendation

logger = logging.getLogger(__name__)

# ── eMode カテゴリ定義 ───────────────────────────────────────────────────────
# Aave V3 Arbitrum Mainnet の Liquid eMode カテゴリ。
# LTV / liquidationThreshold は bps 単位 (10000 = 100%)。
# 実 on-chain 値は UiPoolDataProvider.getEModes() で取得すべきだが、
# Arbitrum Mainnet の公式値は以下の通り (2026-06-15 確認)。
# FLAG: UiPoolDataProviderアドレスが未確定のため、定数で暫定定義。
#        オンチェーン取得への切替は後続タスクで実施する。

EMODE_CATEGORIES: dict[int, EModeInfo] = {
    0: EModeInfo(
        category_id=0,
        label="eMode なし",
        ltv_bps=Decimal("7500"),
        liquidation_threshold_bps=Decimal("8000"),
    ),
    1: EModeInfo(
        category_id=1,
        label="ステーブルコイン",
        ltv_bps=Decimal("9000"),
        liquidation_threshold_bps=Decimal("9300"),
    ),
    2: EModeInfo(
        category_id=2,
        label="ETH 相関",
        ltv_bps=Decimal("9000"),
        liquidation_threshold_bps=Decimal("9300"),
    ),
}

# カテゴリ判定用の資産セット（大文字小文字非依存で使用する）
_STABLE_ASSETS: frozenset[str] = frozenset(["USDC", "USDT", "DAI", "USDC.E", "USDT.E"])
_ETH_ASSETS: frozenset[str] = frozenset(["ETH", "WETH", "WSTETH", "RETH", "CBETH"])


def _normalize(symbol: str) -> str:
    """資産シンボルを大文字・トリムに正規化する。"""
    return symbol.strip().upper()


def recommend_emode(
    current_collateral_assets: list[str],
    current_category_id: int = 0,
) -> EModeRecommendation:
    """
    現在の担保資産構成から最適な eMode カテゴリを推奨する。

    Args:
        current_collateral_assets: 現在の担保資産シンボル一覧
        current_category_id: 現在の eMode カテゴリ ID

    Returns:
        EModeRecommendation: 推奨結果（Decimal 計算）

    ルール:
        - USDC/USDT/DAI のみ → categoryId=1 (ステーブル)
        - ETH/wstETH/rETH のみ → categoryId=2 (ETH)
        - 混合 or 不明 → categoryId=0 (eMode なし)
    """
    normalized = [_normalize(s) for s in current_collateral_assets]

    has_stable = any(s in _STABLE_ASSETS for s in normalized)
    has_eth = any(s in _ETH_ASSETS for s in normalized)
    has_other = any(s not in _STABLE_ASSETS and s not in _ETH_ASSETS for s in normalized)

    if normalized and has_stable and not has_eth and not has_other:
        recommended_id = 1
        reason = "担保資産がすべてステーブルコイン（USDC/USDT/DAI）のため、ステーブル eMode を推奨"
    elif normalized and has_eth and not has_stable and not has_other:
        recommended_id = 2
        reason = "担保資産がすべて ETH 相関資産（ETH/wstETH/rETH）のため、ETH eMode を推奨"
    else:
        recommended_id = 0
        reason = "担保資産が混合またはステーブル/ETH 非対応のため、eMode なし（cat0）を推奨"

    current_info = EMODE_CATEGORIES.get(current_category_id, EMODE_CATEGORIES[0])
    recommended_info = EMODE_CATEGORIES.get(recommended_id, EMODE_CATEGORIES[0])

    current_ltv = current_info.ltv_bps
    recommended_ltv = recommended_info.ltv_bps

    # LTV 改善率の計算（Decimal のみ、float 禁止）
    # 改善率 = (recommended_ltv - current_ltv) / current_ltv * 100
    if current_ltv > Decimal("0"):
        ltv_improvement_pct = (recommended_ltv - current_ltv) / current_ltv * Decimal("100")
    else:
        ltv_improvement_pct = Decimal("0")

    logger.info(
        "eMode 推奨: assets=%s, current_cat=%d (ltv=%sbps), recommended_cat=%d (ltv=%sbps), "
        "improvement=%.2f%%",
        normalized,
        current_category_id,
        current_ltv,
        recommended_id,
        recommended_ltv,
        float(ltv_improvement_pct),  # ログのみ float 許容
    )

    return EModeRecommendation(
        current_category_id=current_category_id,
        recommended_category_id=recommended_id,
        current_ltv_bps=current_ltv,
        recommended_ltv_bps=recommended_ltv,
        ltv_improvement_pct=ltv_improvement_pct,
        reason=reason,
        collateral_assets=normalized,
    )


def get_emode_info(category_id: int) -> EModeInfo:
    """
    eMode カテゴリ ID から EModeInfo を返す。
    未知のカテゴリ ID は cat0 (eMode なし) として扱う（fail-open）。
    """
    return EMODE_CATEGORIES.get(category_id, EMODE_CATEGORIES[0])
