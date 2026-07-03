# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""GHO 借入シグナル Phase 1（観測のみ）の非破壊性テスト。

MarketContext.gho_borrow_signal は追加するが、既存の BUY/SELL/HOLD 判定
サーフェス（4 エージェント / Guard1 / Guard2 / プロンプト生成）には一切
影響させない設計（2026-07-03 Plan mode で検証済み）。本ファイルはその
不変条件を構造的に保証する回帰テスト。
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

from app.ai import agents as agents_module
from app.ai.agents import run_all_agents
from app.ai.schemas import RAGContext
from app.ai.service import AIService
from app.data_feeds.context import build_market_context


class TestStaticTripwire:
    """agents.py のソースに gho_borrow_signal という文字列が一切出現しないこと。

    将来の PR が「5th agent」的に混入させたら即座に落ちる静的ガード
    （Planエージェント設計: 4軸固定構造への誤混入防止）。
    """

    def test_agents_source_does_not_reference_gho_signal(self) -> None:
        source_path = Path(inspect.getfile(agents_module))
        source = source_path.read_text(encoding="utf-8")
        assert "gho_borrow_signal" not in source
        assert "gho" not in source.lower()


class TestRunAllAgentsIdentity:
    """gho_borrow_signal の値に関わらず run_all_agents() の出力が完全一致すること。"""

    def _contexts(self):
        base_kwargs = dict(
            health_factor=Decimal("1.75"),
            aave_utilization_rate=Decimal("60"),
            aave_supply_apy=Decimal("4.0"),
            aave_borrow_apy=Decimal("6.0"),
        )
        ctx_without = build_market_context(**base_kwargs, gho_borrow_signal=None)
        ctx_with = build_market_context(**base_kwargs, gho_borrow_signal="recommend_gho")
        return ctx_without, ctx_with

    def test_multi_agent_context_identical(self) -> None:
        ctx_without, ctx_with = self._contexts()
        result_without = run_all_agents(ctx_without)
        result_with = run_all_agents(ctx_with)

        assert result_without.model_dump() == result_with.model_dump()

    def test_compound_risk_and_agreement_flags_identical(self) -> None:
        ctx_without, ctx_with = self._contexts()
        result_without = run_all_agents(ctx_without)
        result_with = run_all_agents(ctx_with)

        assert result_without.has_compound_risk() == result_with.has_compound_risk()
        assert (
            result_without.indicator_and_macro_agree_bearish()
            == result_with.indicator_and_macro_agree_bearish()
        )
        assert (
            result_without.indicator_and_macro_agree_bullish()
            == result_with.indicator_and_macro_agree_bullish()
        )

    def test_recommend_usdc_also_identical(self) -> None:
        """recommend_usdc / recommend_gho / None の3パターンとも同一結果。"""
        base_kwargs = dict(
            health_factor=Decimal("2.2"),
            aave_utilization_rate=Decimal("30"),
        )
        results = [
            run_all_agents(build_market_context(**base_kwargs, gho_borrow_signal=v))
            for v in (None, "recommend_gho", "recommend_usdc")
        ]
        dumps = [r.model_dump() for r in results]
        assert dumps[0] == dumps[1] == dumps[2]


class TestPromptGenerationUnaffected:
    """Phase 1 はプロンプト注入をしないため、_build_rag_prompt の出力が
    gho_borrow_signal の値に関わらずバイト単位で完全一致すること。
    """

    def test_build_rag_prompt_byte_identical_across_gho_values(self) -> None:
        service = AIService.__new__(AIService)  # __init__ の外部API依存を回避
        rag_context = RAGContext(chunks=["dummy chunk"], query="test query", source_count=1)

        base_kwargs = dict(
            health_factor=Decimal("1.9"),
            aave_utilization_rate=Decimal("55"),
        )
        for version in ("v1", "v3", "v4", "v5"):
            ctx_without = build_market_context(**base_kwargs, gho_borrow_signal=None)
            ctx_with = build_market_context(**base_kwargs, gho_borrow_signal="recommend_gho")

            sys_without, user_without = service._build_rag_prompt(
                query="test query",
                rag_context=rag_context,
                version=version,
                market_context=ctx_without,
            )
            sys_with, user_with = service._build_rag_prompt(
                query="test query",
                rag_context=rag_context,
                version=version,
                market_context=ctx_with,
            )

            assert sys_without == sys_with, f"system_prompt differs for version={version}"
            assert user_without == user_with, f"user_content differs for version={version}"
