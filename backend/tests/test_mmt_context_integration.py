# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""結合テスト: mmt_feed → context → ai/service の統合フロー。

カバレッジ:
A. mmt_feed → context 統合
   - MMT_API_ENABLED=true 時: キャッシュがcontextプロンプトに反映される
   - MMT_API_ENABLED=false 時: contextにMMTデータが含まれない
   - mmt_feed エラー時: contextがフォールバック（MMTなし）で構築される

B. context → ai/service 統合
   - MMTデータ入りcontextがai/serviceのプロンプト構築に使われること
   - MMTデータなしcontextでも正常動作すること

C. エンドツーエンド（HTTPモック付き）
   - fetch_mmt_data (HTTP モック) → build_market_context → judge_with_rag (LLMモック)
   - 最終プロンプトにMMTセクションが含まれることを検証
"""

import dataclasses
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.data_feeds.mmt_feed as mmt_module
from app.data_feeds.mmt_feed import (
    MMTData,
    MMTOpenInterest,
    MMTStats,
    fetch_mmt_data,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_mmt_data_with_content() -> MMTData:
    """アサーション可能なMMTDataを返す（Funding Rate + OI 付き）。"""
    return MMTData(
        stats=[
            MMTStats(
                symbol="btc/usd",
                exchange="binancef",
                funding_rate=Decimal("0.000125"),
            ),
            MMTStats(
                symbol="eth/usd",
                exchange="binancef",
                funding_rate=Decimal("-0.000050"),
            ),
        ],
        open_interest=[
            MMTOpenInterest(
                symbol="btc/usd",
                exchange="binancef",
                open_interest=Decimal("12500000000"),
                oi_change_pct=3.2,
            ),
        ],
    )


def _reset_mmt_cache() -> None:
    mmt_module._cached_mmt = None
    mmt_module._previous_oi.clear()


def _make_test_settings() -> object:
    """テスト用 AISettings（LLM API呼び出しなし）。"""
    from app.ai.config import get_ai_settings

    return dataclasses.replace(
        get_ai_settings(),
        anthropic_api_key="dummy",
        cross_validation_enabled=False,
        shadow_mode=False,
    )


# ---------------------------------------------------------------------------
# A. mmt_feed → context 統合
# ---------------------------------------------------------------------------


class TestMMTFeedToContext:
    """fetch_mmt_data のキャッシュ更新が MarketContext に反映される。"""

    def setup_method(self) -> None:
        _reset_mmt_cache()

    def teardown_method(self) -> None:
        _reset_mmt_cache()

    # ------------------------------------------------------------------
    # A-1: MMT_API_ENABLED=true — キャッシュがpromptに含まれる
    # ------------------------------------------------------------------

    def test_enabled_cache_appears_in_context_prompt(self) -> None:
        """キャッシュに MMTData があれば context.to_prompt_context() に MMT セクションが入る。"""
        from app.data_feeds.context import build_market_context

        mmt = _make_mmt_data_with_content()
        mmt_module._cached_mmt = mmt

        ctx = build_market_context()
        prompt = ctx.to_prompt_context()

        assert "MMT Market Data" in prompt
        assert "btc/usd Funding Rate" in prompt
        assert "ロング過多" in prompt
        assert "eth/usd Funding Rate" in prompt
        assert "ショート過多" in prompt
        assert "btc/usd OI" in prompt
        assert "+3.20%" in prompt

    # ------------------------------------------------------------------
    # A-2: MMT_API_ENABLED=false — contextにMMTデータが含まれない
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_disabled_no_mmt_in_context(self) -> None:
        """MMT_API_ENABLED=false の場合、fetch_mmt_data() は None を返しキャッシュを更新しない。"""
        from app.data_feeds.context import build_market_context

        with patch.dict(os.environ, {"MMT_API_ENABLED": "false", "MMT_API_KEY": "dummy-key"}):
            result = await fetch_mmt_data()

        assert result is None
        assert mmt_module._cached_mmt is None

        ctx = build_market_context()
        prompt = ctx.to_prompt_context()
        assert "MMT Market Data" not in prompt

    @pytest.mark.asyncio
    async def test_no_api_key_no_mmt_in_context(self) -> None:
        """MMT_API_KEY 未設定の場合も同様にキャッシュが更新されない。"""
        from app.data_feeds.context import build_market_context

        env = {"MMT_API_ENABLED": "true"}
        with patch.dict(os.environ, env):
            os.environ.pop("MMT_API_KEY", None)
            result = await fetch_mmt_data()

        assert result is None
        ctx = build_market_context()
        assert "MMT Market Data" not in ctx.to_prompt_context()

    # ------------------------------------------------------------------
    # A-3: mmt_feed HTTP エラー時 — context はフォールバック（MMTなし）で動く
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_api_error_context_fallback_no_mmt(self) -> None:
        """fetch_mmt_data 内で全エンドポイントが HTTP 500 → キャッシュ更新されるがデータは空。"""
        from app.data_feeds.context import build_market_context

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"MMT_API_ENABLED": "true", "MMT_API_KEY": "test-key"}):
            with patch("app.data_feeds.mmt_feed.httpx.AsyncClient", return_value=mock_client):
                result = await fetch_mmt_data()

        # fetch_mmt_data returns an empty MMTData (not None) — cache was updated
        assert result is not None
        assert result.stats == []
        assert result.open_interest == []

        # build_market_context picks up the empty MMTData from cache.
        # to_prompt_section() returns "" for empty data → "MMT Market Data" not in prompt.
        ctx = build_market_context()
        prompt = ctx.to_prompt_context()
        assert "MMT Market Data" not in prompt

    def test_mmt_data_none_in_context_skips_section(self) -> None:
        """mmt_data が None のとき to_prompt_context() は MMT セクションを出力しない。"""
        from app.data_feeds.context import MarketContext

        ctx = MarketContext(mmt_data=None)
        prompt = ctx.to_prompt_context()
        assert "MMT Market Data" not in prompt

    def test_empty_mmt_data_in_context_skips_section(self) -> None:
        """stats/OI が空の MMTData は to_prompt_section() が "" を返す → promptに含まれない。"""
        from app.data_feeds.context import MarketContext

        ctx = MarketContext(mmt_data=MMTData())
        prompt = ctx.to_prompt_context()
        assert "MMT Market Data" not in prompt


# ---------------------------------------------------------------------------
# B. context → ai/service 統合
# ---------------------------------------------------------------------------


class TestContextToAIService:
    """MarketContext の MMT データが judge_with_rag のプロンプト構築に反映される。"""

    def setup_method(self) -> None:
        _reset_mmt_cache()

    def teardown_method(self) -> None:
        _reset_mmt_cache()

    def _make_service_with_captured_prompt(self) -> tuple[object, list[str]]:
        """AIService と、_call_claude に渡された user_content を記録するリストを返す。"""
        from app.ai.schemas import LLMDecision, LLMProvider, TradeAction
        from app.ai.service import AIService

        captured: list[str] = []
        fixed_decision = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.HOLD,
            confidence=70,
            reason="test",
            prompt_version="v1",
        )

        def fake_call_claude(
            system_prompt: str, user_content: str, settings: object, version: str = "v1"
        ) -> LLMDecision:
            captured.append(user_content)
            return fixed_decision

        svc = AIService()
        svc._call_claude = fake_call_claude  # type: ignore[method-assign]
        return svc, captured

    # ------------------------------------------------------------------
    # B-1: MMTデータ入りcontextがプロンプトに反映される
    # ------------------------------------------------------------------

    def test_mmt_data_appears_in_judge_prompt(self) -> None:
        """judge_with_rag に MMTデータ入り MarketContext を渡すと LLM への入力に MMT セクションが含まれる。"""
        from app.ai.schemas import RAGContext
        from app.data_feeds.context import MarketContext

        mmt = _make_mmt_data_with_content()
        ctx = MarketContext(mmt_data=mmt)
        rag = RAGContext(query="BTC/USDトレード判断", chunks=["BTC is rising."], source_count=1)

        svc, captured = self._make_service_with_captured_prompt()

        svc.judge_with_rag(
            "BTC/USDトレード判断", rag, market_context=ctx, settings=_make_test_settings()
        )

        assert len(captured) == 1
        prompt_text = captured[0]
        assert "MMT Market Data" in prompt_text
        assert "btc/usd Funding Rate" in prompt_text
        assert "ロング過多" in prompt_text

    # ------------------------------------------------------------------
    # B-2: MMTデータなしcontextでも正常動作
    # ------------------------------------------------------------------

    def test_no_mmt_context_judge_works_normally(self) -> None:
        """MMT データなし MarketContext でも judge_with_rag が正常に完了する。"""
        from app.ai.schemas import CrossValidationResult, RAGContext, TradeAction
        from app.data_feeds.context import MarketContext

        ctx = MarketContext(mmt_data=None)
        rag = RAGContext(query="ETH/USDトレード判断", chunks=["ETH news."], source_count=1)

        svc, captured = self._make_service_with_captured_prompt()

        result = svc.judge_with_rag(
            "ETH/USDトレード判断", rag, market_context=ctx, settings=_make_test_settings()
        )

        assert isinstance(result, CrossValidationResult)
        assert result.final_action == TradeAction.HOLD
        # MMT セクションがプロンプトに含まれていないこと
        assert len(captured) == 1
        assert "MMT Market Data" not in captured[0]

    # ------------------------------------------------------------------
    # B-3: market_context=None でも judge_with_rag は動く
    # ------------------------------------------------------------------

    def test_none_market_context_judge_works(self) -> None:
        """market_context を渡さなくても judge_with_rag が正常完了する。"""
        from app.ai.schemas import CrossValidationResult, RAGContext, TradeAction

        rag = RAGContext(query="テスト", chunks=["context."], source_count=1)

        svc, captured = self._make_service_with_captured_prompt()

        result = svc.judge_with_rag("テスト", rag, settings=_make_test_settings())

        assert isinstance(result, CrossValidationResult)
        assert result.final_action == TradeAction.HOLD
        assert "MMT Market Data" not in captured[0]

    # ------------------------------------------------------------------
    # B-4: _build_rag_prompt が MMTセクションをプロンプトに含める（直接検証）
    # ------------------------------------------------------------------

    def test_build_rag_prompt_includes_mmt_section(self) -> None:
        """_build_rag_prompt が Market Context (with MMT) を user_content に埋め込む。"""
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService
        from app.data_feeds.context import MarketContext

        mmt = _make_mmt_data_with_content()
        ctx = MarketContext(mmt_data=mmt)
        rag = RAGContext(query="テスト", chunks=["test chunk"], source_count=1)

        svc = AIService()
        _system, user_content = svc._build_rag_prompt(
            "テスト",
            rag,
            version="v1",
            market_context=ctx,
        )

        assert "MMT Market Data" in user_content
        assert "btc/usd Funding Rate" in user_content
        assert "Market Context (Real-time Data)" in user_content

    def test_build_rag_prompt_no_mmt_excludes_section(self) -> None:
        """_build_rag_prompt に MMT なし MarketContext を渡すと MMT セクションがない。"""
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService
        from app.data_feeds.context import MarketContext

        ctx = MarketContext(mmt_data=None)
        rag = RAGContext(query="テスト", chunks=["test chunk"], source_count=1)

        svc = AIService()
        _system, user_content = svc._build_rag_prompt(
            "テスト",
            rag,
            version="v1",
            market_context=ctx,
        )

        assert "MMT Market Data" not in user_content
        assert "Market Context (Real-time Data)" in user_content


# ---------------------------------------------------------------------------
# C. エンドツーエンド（HTTPモック + LLMモック）
# ---------------------------------------------------------------------------


class TestMMTEndToEnd:
    """mmt_feed HTTP モック → context 構築 → ai/service LLM モック の完全フロー。"""

    def setup_method(self) -> None:
        _reset_mmt_cache()

    def teardown_method(self) -> None:
        _reset_mmt_cache()

    # ------------------------------------------------------------------
    # C-1: fetch_mmt_data (HTTPモック) → build_market_context → judge_with_rag
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_flow_mmt_data_reaches_ai_prompt(self) -> None:
        """HTTP モックで fetch_mmt_data を完走させ、MMTデータが最終AIプロンプトに届くことを確認。"""
        from app.data_feeds.context import build_market_context

        # --- HTTPモック: stats / oi / candles 各エンドポイント ---
        call_count = 0
        responses = [
            # btc/usd stats
            {"data": [{"fr": 0.000125, "bd": None, "ad": None, "t": 1700000000}]},
            # btc/usd oi
            {"data": [{"oi": 12500000000, "t": 1700000000}]},
            # btc/usd candles
            {"data": []},
            # eth/usd stats
            {"data": [{"fr": -0.000050, "bd": None, "ad": None, "t": 1700000000}]},
            # eth/usd oi
            {"data": [{"oi": 5000000000, "t": 1700000000}]},
            # eth/usd candles
            {"data": []},
        ]

        async def mock_get(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = responses[call_count % len(responses)]
            call_count += 1
            return resp

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.dict(os.environ, {"MMT_API_ENABLED": "true", "MMT_API_KEY": "test-key"}):
            with patch("app.data_feeds.mmt_feed.httpx.AsyncClient", return_value=mock_client):
                mmt_result = await fetch_mmt_data()

        assert mmt_result is not None
        assert len(mmt_result.stats) == 2
        assert len(mmt_result.open_interest) == 2

        # --- context 構築: キャッシュから MMTData が取れる ---
        ctx = build_market_context()
        assert ctx.mmt_data is mmt_result
        prompt_section = ctx.to_prompt_context()
        assert "MMT Market Data" in prompt_section
        assert "btc/usd Funding Rate" in prompt_section
        assert "ロング過多" in prompt_section
        assert "eth/usd Funding Rate" in prompt_section
        assert "ショート過多" in prompt_section

    @pytest.mark.asyncio
    async def test_full_flow_judge_with_rag_receives_mmt(self) -> None:
        """fetch_mmt_data (HTTP モック) → judge_with_rag (LLM モック): 最終プロンプトにMMTが含まれる。"""
        from app.ai.schemas import LLMDecision, LLMProvider, RAGContext, TradeAction
        from app.ai.service import AIService

        # --- MMTキャッシュをセット（HTTPモックの代わりに直接注入） ---
        mmt_module._cached_mmt = _make_mmt_data_with_content()

        captured_prompts: list[str] = []
        fixed_decision = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.HOLD,
            confidence=65,
            reason="テスト判定",
            prompt_version="v1",
        )

        def fake_call_claude(
            system_prompt: str, user_content: str, settings: object, version: str = "v1"
        ) -> LLMDecision:
            captured_prompts.append(user_content)
            return fixed_decision

        svc = AIService()
        svc._call_claude = fake_call_claude  # type: ignore[method-assign]

        from app.data_feeds.context import build_market_context

        ctx = build_market_context()
        rag = RAGContext(
            query="BTC現在の市場判断をしてください",
            chunks=["BTC価格は上昇トレンド。"],
            source_count=1,
        )

        settings = _make_test_settings()
        result = svc.judge_with_rag(
            "BTC現在の市場判断をしてください", rag, market_context=ctx, settings=settings
        )

        # LLMが呼ばれ、プロンプトにMMTデータが含まれる
        assert len(captured_prompts) == 1
        final_prompt = captured_prompts[0]
        assert "MMT Market Data" in final_prompt
        assert "btc/usd Funding Rate" in final_prompt
        assert "BTC価格は上昇トレンド" in final_prompt  # RAGチャンクも含まれる

        # 判定結果が返る
        from app.ai.schemas import CrossValidationResult

        assert isinstance(result, CrossValidationResult)
        assert result.final_action == TradeAction.HOLD

    @pytest.mark.asyncio
    async def test_full_flow_disabled_no_mmt_in_judge_prompt(self) -> None:
        """MMT無効時: judge_with_rag のプロンプトに MMT セクションが含まれない。"""
        from app.ai.schemas import LLMDecision, LLMProvider, RAGContext, TradeAction
        from app.ai.service import AIService
        from app.data_feeds.context import build_market_context

        # キャッシュは None のまま（setup_method でリセット済み）
        ctx = build_market_context()
        assert ctx.mmt_data is None

        captured_prompts: list[str] = []
        fixed_decision = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.HOLD,
            confidence=50,
            reason="test",
            prompt_version="v1",
        )

        def fake_call_claude(
            system_prompt: str, user_content: str, settings: object, version: str = "v1"
        ) -> LLMDecision:
            captured_prompts.append(user_content)
            return fixed_decision

        svc = AIService()
        svc._call_claude = fake_call_claude  # type: ignore[method-assign]

        rag = RAGContext(query="テスト", chunks=["chunk"], source_count=1)

        svc.judge_with_rag("テスト", rag, market_context=ctx, settings=_make_test_settings())

        assert len(captured_prompts) == 1
        assert "MMT Market Data" not in captured_prompts[0]

    # ------------------------------------------------------------------
    # C-2: MMT_API_ENABLED 切り替えの整合性
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_enabled_then_disabled_clears_mmt_from_next_fetch(self) -> None:
        """有効→無効の切り替え: disabled 後の fetch は None を返し既存キャッシュに触らない。"""
        # 事前にキャッシュを設定（有効時の状態をシミュレート）
        mmt_module._cached_mmt = _make_mmt_data_with_content()
        existing_cache = mmt_module._cached_mmt

        # 無効状態で fetch
        with patch.dict(os.environ, {"MMT_API_ENABLED": "false", "MMT_API_KEY": "key"}):
            result = await fetch_mmt_data()

        # fetch は None を返すが、既存キャッシュは変更されない
        assert result is None
        assert mmt_module._cached_mmt is existing_cache  # 既存キャッシュそのまま

    @pytest.mark.asyncio
    async def test_monkeypatch_env_disables_mmt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """monkeypatch.setenv で MMT_API_ENABLED を切り替えできることを確認。"""
        monkeypatch.setenv("MMT_API_ENABLED", "false")
        monkeypatch.setenv("MMT_API_KEY", "some-key")

        result = await fetch_mmt_data()
        assert result is None

    @pytest.mark.asyncio
    async def test_monkeypatch_env_enables_mmt_requires_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """monkeypatch.setenv で MMT_API_ENABLED=true かつ KEY 空の場合は None。"""
        monkeypatch.setenv("MMT_API_ENABLED", "true")
        monkeypatch.delenv("MMT_API_KEY", raising=False)

        result = await fetch_mmt_data()
        assert result is None
