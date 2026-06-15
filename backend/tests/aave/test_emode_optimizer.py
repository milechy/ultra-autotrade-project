# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/aave/test_emode_optimizer.py
"""
emode_optimizer のユニットテスト。

テスト要件:
- [USDC, USDT] → cat1 (ステーブル)
- [ETH, wstETH] → cat2 (ETH)
- [USDC, ETH] → cat0 (混合)
- LTV 改善率が正しく計算される (75% → 90% = +20.0%)
- 大文字小文字非依存の動作確認
"""

from __future__ import annotations

from decimal import Decimal

from app.aave.emode_optimizer import (
    EMODE_CATEGORIES,
    _normalize,
    get_emode_info,
    recommend_emode,
)
from app.aave.schemas import EModeInfo, EModeRecommendation


class TestNormalize:
    """_normalize ユーティリティのテスト。"""

    def test_uppercase(self) -> None:
        assert _normalize("usdc") == "USDC"

    def test_trim(self) -> None:
        assert _normalize("  USDT  ") == "USDT"

    def test_already_upper(self) -> None:
        assert _normalize("ETH") == "ETH"


class TestEmodeCategories:
    """EMODE_CATEGORIES 定数のテスト。"""

    def test_cat0_ltv(self) -> None:
        cat0 = EMODE_CATEGORIES[0]
        assert cat0.ltv_bps == Decimal("7500")
        assert cat0.category_id == 0

    def test_cat1_ltv(self) -> None:
        cat1 = EMODE_CATEGORIES[1]
        assert cat1.ltv_bps == Decimal("9000")
        assert cat1.category_id == 1

    def test_cat2_ltv(self) -> None:
        cat2 = EMODE_CATEGORIES[2]
        assert cat2.ltv_bps == Decimal("9000")
        assert cat2.category_id == 2


class TestGetEmodeInfo:
    """get_emode_info のテスト。"""

    def test_known_category(self) -> None:
        info = get_emode_info(1)
        assert isinstance(info, EModeInfo)
        assert info.category_id == 1

    def test_unknown_category_fallback(self) -> None:
        """未知の ID は cat0 にフォールバック。"""
        info = get_emode_info(99)
        assert info.category_id == 0


class TestRecommendEmode:
    """recommend_emode のテスト。"""

    def test_stable_only_recommends_cat1(self) -> None:
        """USDC + USDT のみ → cat1 推奨。"""
        result = recommend_emode(
            current_collateral_assets=["USDC", "USDT"],
            current_category_id=0,
        )
        assert isinstance(result, EModeRecommendation)
        assert result.recommended_category_id == 1
        assert result.current_category_id == 0

    def test_dai_included_recommends_cat1(self) -> None:
        """DAI を含むステーブルのみ → cat1 推奨。"""
        result = recommend_emode(
            current_collateral_assets=["USDC", "DAI"],
            current_category_id=0,
        )
        assert result.recommended_category_id == 1

    def test_eth_only_recommends_cat2(self) -> None:
        """ETH + wstETH のみ → cat2 推奨。"""
        result = recommend_emode(
            current_collateral_assets=["ETH", "wstETH"],
            current_category_id=0,
        )
        assert result.recommended_category_id == 2

    def test_reth_only_recommends_cat2(self) -> None:
        """rETH のみ → cat2 推奨。"""
        result = recommend_emode(
            current_collateral_assets=["rETH"],
            current_category_id=0,
        )
        assert result.recommended_category_id == 2

    def test_mixed_recommends_cat0(self) -> None:
        """USDC + ETH 混合 → cat0 推奨。"""
        result = recommend_emode(
            current_collateral_assets=["USDC", "ETH"],
            current_category_id=0,
        )
        assert result.recommended_category_id == 0

    def test_empty_list_recommends_cat0(self) -> None:
        """担保資産なし → cat0 推奨。"""
        result = recommend_emode(
            current_collateral_assets=[],
            current_category_id=0,
        )
        assert result.recommended_category_id == 0

    def test_unknown_asset_recommends_cat0(self) -> None:
        """未知の資産 → cat0 推奨。"""
        result = recommend_emode(
            current_collateral_assets=["SHIB"],
            current_category_id=0,
        )
        assert result.recommended_category_id == 0

    def test_case_insensitive_stable(self) -> None:
        """小文字でも正しく判定される。"""
        result = recommend_emode(
            current_collateral_assets=["usdc", "usdt"],
            current_category_id=0,
        )
        assert result.recommended_category_id == 1

    def test_case_insensitive_eth(self) -> None:
        """wsteth など小文字でも ETH eMode に判定される。"""
        result = recommend_emode(
            current_collateral_assets=["wsteth"],
            current_category_id=0,
        )
        assert result.recommended_category_id == 2

    def test_ltv_improvement_from_cat0_to_cat1(self) -> None:
        """LTV 改善率の計算: cat0 (7500bps=75%) → cat1 (9000bps=90%) = +20.0%"""
        result = recommend_emode(
            current_collateral_assets=["USDC", "USDT"],
            current_category_id=0,
        )
        assert result.current_ltv_bps == Decimal("7500")
        assert result.recommended_ltv_bps == Decimal("9000")
        # 改善率 = (9000 - 7500) / 7500 * 100 = 20.0
        expected_improvement = (
            (Decimal("9000") - Decimal("7500")) / Decimal("7500") * Decimal("100")
        )
        assert result.ltv_improvement_pct == expected_improvement
        assert result.ltv_improvement_pct == Decimal("20")

    def test_ltv_improvement_is_decimal(self) -> None:
        """LTV 改善率が Decimal 型であることを確認 (float 禁止)。"""
        result = recommend_emode(
            current_collateral_assets=["USDC"],
            current_category_id=0,
        )
        assert isinstance(result.ltv_improvement_pct, Decimal)
        assert isinstance(result.current_ltv_bps, Decimal)
        assert isinstance(result.recommended_ltv_bps, Decimal)

    def test_no_improvement_when_already_optimal(self) -> None:
        """既に最適な cat1 なら改善率 0。"""
        result = recommend_emode(
            current_collateral_assets=["USDC", "USDT"],
            current_category_id=1,
        )
        assert result.recommended_category_id == 1
        assert result.ltv_improvement_pct == Decimal("0")

    def test_collateral_assets_normalized_in_result(self) -> None:
        """結果の collateral_assets は大文字に正規化されている。"""
        result = recommend_emode(
            current_collateral_assets=["usdc", "usdt"],
            current_category_id=0,
        )
        assert "USDC" in result.collateral_assets
        assert "USDT" in result.collateral_assets

    def test_reason_is_nonempty(self) -> None:
        """reason フィールドは空でない。"""
        result = recommend_emode(
            current_collateral_assets=["USDC"],
            current_category_id=0,
        )
        assert len(result.reason) > 0

    def test_serialization(self) -> None:
        """Pydantic model_dump でシリアライズ可能であることを確認。"""
        result = recommend_emode(
            current_collateral_assets=["USDC", "USDT"],
            current_category_id=0,
        )
        dumped = result.model_dump()
        assert "recommended_category_id" in dumped
        # Decimal は文字列にシリアライズされる
        serialized = result.model_dump(mode="json")
        assert isinstance(serialized["ltv_improvement_pct"], str)


class TestEModeInfoSchema:
    """EModeInfo スキーマのシリアライゼーションテスト。"""

    def test_ltv_serialized_as_string(self) -> None:
        """ltv_bps は JSON シリアライズで文字列になる。"""
        info = EMODE_CATEGORIES[1]
        d = info.model_dump(mode="json")
        assert isinstance(d["ltv_bps"], str)
        assert d["ltv_bps"] == "9000"

    def test_liquidation_threshold_serialized_as_string(self) -> None:
        info = EMODE_CATEGORIES[1]
        d = info.model_dump(mode="json")
        assert isinstance(d["liquidation_threshold_bps"], str)
