# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for data_feeds/context.py — MarketContext and build_market_context."""

import os
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-context-key")

from app.data_feeds.context import MarketContext, build_market_context  # noqa: E402
from app.data_feeds.finance_feed import FinanceFeedResult  # noqa: E402
from app.data_feeds.geopolitical import GeoRiskResult  # noqa: E402
from app.data_feeds.mmt_feed import MMTData, MMTOpenInterest, MMTStats  # noqa: E402
from app.data_feeds.news_feed import NewsFeedResult  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_geo(score: int = 30, summary: str = "Low risk") -> GeoRiskResult:
    return GeoRiskResult(geo_risk_score=score, summary=summary)


def _make_news(
    summary: str = "Crypto markets stable.",
    sentiment: str = "neutral",
    key_events: list[str] | None = None,
) -> NewsFeedResult:
    return NewsFeedResult(
        summary=summary,
        sentiment=sentiment,
        key_events=key_events or [],
    )


def _make_finance(
    macro_summary: str = "Fed holds rates steady.",
    fed_stance: str = "neutral",
    stablecoin_risk: str = "low",
    key_indicators: list[str] | None = None,
) -> FinanceFeedResult:
    return FinanceFeedResult(
        macro_summary=macro_summary,
        fed_stance=fed_stance,
        stablecoin_risk=stablecoin_risk,
        key_indicators=key_indicators or [],
    )


def _make_mmt_data(
    funding_rate: str = "0.000125",
    oi: str = "1500000000",
    oi_change_pct: float = 2.5,
) -> MMTData:
    stats = [
        MMTStats(
            symbol="btc/usd",
            exchange="binancef",
            funding_rate=Decimal(funding_rate),
        )
    ]
    open_interest = [
        MMTOpenInterest(
            symbol="btc/usd",
            exchange="binancef",
            open_interest=Decimal(oi),
            oi_change_pct=oi_change_pct,
        )
    ]
    return MMTData(stats=stats, open_interest=open_interest)


# ---------------------------------------------------------------------------
# 1. MarketContext デフォルト値
# ---------------------------------------------------------------------------


class TestMarketContextDefaults:
    def test_aave_fields_default_none(self) -> None:
        """Aave 関連フィールドはデフォルト None。"""
        ctx = MarketContext(
            geo_risk=_make_geo(),
            news=_make_news(),
            finance=_make_finance(),
        )
        assert ctx.aave_utilization_rate is None
        assert ctx.aave_supply_apy is None
        assert ctx.aave_borrow_apy is None
        assert ctx.health_factor is None
        assert ctx.mmt_data is None
        assert ctx.social_sentiment_score is None
        assert ctx.cognitive_state is None

    def test_collected_at_is_set(self) -> None:
        """collected_at が自動的に設定される。"""
        ctx = MarketContext(
            geo_risk=_make_geo(),
            news=_make_news(),
            finance=_make_finance(),
        )
        assert ctx.collected_at is not None

    def test_all_fields_can_be_set(self) -> None:
        """全フィールドを明示的に設定できる。"""
        mmt = _make_mmt_data()
        ctx = MarketContext(
            geo_risk=_make_geo(score=60),
            news=_make_news(summary="BTC surges 10%.", sentiment="positive"),
            finance=_make_finance(fed_stance="dovish"),
            aave_utilization_rate=Decimal("87.5"),
            aave_supply_apy=Decimal("4.2"),
            aave_borrow_apy=Decimal("6.1"),
            health_factor=Decimal("1.72"),
            mmt_data=mmt,
            social_sentiment_score=Decimal("72"),
        )
        assert ctx.geo_risk.geo_risk_score == 60
        assert ctx.aave_utilization_rate == Decimal("87.5")
        assert ctx.health_factor == Decimal("1.72")
        assert ctx.mmt_data is mmt
        assert ctx.social_sentiment_score == Decimal("72")


# ---------------------------------------------------------------------------
# 2. build_market_context()
# ---------------------------------------------------------------------------


class TestBuildMarketContext:
    def test_returns_market_context_instance(self) -> None:
        """build_market_context() は MarketContext を返す。"""
        with (
            patch("app.data_feeds.context.get_cached_geo_risk", return_value=_make_geo()),
            patch("app.data_feeds.context.get_cached_news", return_value=_make_news()),
            patch("app.data_feeds.context.get_cached_finance", return_value=_make_finance()),
            patch("app.data_feeds.context.get_cached_mmt_data", return_value=None),
        ):
            ctx = build_market_context()
        assert isinstance(ctx, MarketContext)

    def test_overrides_are_applied(self) -> None:
        """キーワード引数でのオーバーライドが反映される。"""
        with (
            patch("app.data_feeds.context.get_cached_geo_risk", return_value=_make_geo()),
            patch("app.data_feeds.context.get_cached_news", return_value=_make_news()),
            patch("app.data_feeds.context.get_cached_finance", return_value=_make_finance()),
            patch("app.data_feeds.context.get_cached_mmt_data", return_value=None),
        ):
            ctx = build_market_context(
                health_factor=Decimal("1.85"),
                aave_utilization_rate=Decimal("75.0"),
            )
        assert ctx.health_factor == Decimal("1.85")
        assert ctx.aave_utilization_rate == Decimal("75.0")

    def test_partial_feeds_available(self) -> None:
        """一部フィードのみ利用可能 → 他フィールドは None のまま（エラーにならない）。"""
        with (
            patch("app.data_feeds.context.get_cached_geo_risk", return_value=_make_geo()),
            patch("app.data_feeds.context.get_cached_news", return_value=_make_news()),
            patch("app.data_feeds.context.get_cached_finance", return_value=_make_finance()),
            patch("app.data_feeds.context.get_cached_mmt_data", return_value=None),
        ):
            ctx = build_market_context()
        assert ctx.mmt_data is None
        assert ctx.health_factor is None

    def test_mmt_data_override(self) -> None:
        """MMTData をオーバーライドとして渡せる。"""
        mmt = _make_mmt_data()
        with (
            patch("app.data_feeds.context.get_cached_geo_risk", return_value=_make_geo()),
            patch("app.data_feeds.context.get_cached_news", return_value=_make_news()),
            patch("app.data_feeds.context.get_cached_finance", return_value=_make_finance()),
            patch("app.data_feeds.context.get_cached_mmt_data", return_value=None),
        ):
            ctx = build_market_context(mmt_data=mmt)
        assert ctx.mmt_data is mmt


# ---------------------------------------------------------------------------
# 3. to_prompt_context()
# ---------------------------------------------------------------------------


class TestToPromptContext:
    def _ctx(self, **kwargs: object) -> MarketContext:
        """テスト用 MarketContext を組み立てるヘルパー（デフォルト: 全データあり）。"""
        defaults: dict[str, object] = {
            "geo_risk": _make_geo(score=35, summary="Moderate global tension"),
            "news": _make_news(
                summary="DeFi activity rises.",
                sentiment="positive",
                key_events=["Aave V3 upgrade", "USDC depeg rumour"],
            ),
            "finance": _make_finance(
                macro_summary="Fed holds rates steady.",
                fed_stance="neutral",
                stablecoin_risk="low",
                key_indicators=["CPI 3.2%", "DXY 104"],
            ),
        }
        defaults.update(kwargs)
        return MarketContext(**defaults)

    def test_geo_risk_always_present(self) -> None:
        """[Geopolitical Risk] セクションは常に出力される。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[Geopolitical Risk]" in result
        assert "35" in result
        assert "Moderate global tension" in result

    def test_aave_section_when_set(self) -> None:
        """Aave フィールドが設定されているとき [Aave Market] セクションが含まれる。"""
        ctx = self._ctx(
            aave_utilization_rate=Decimal("87.5"),
            aave_supply_apy=Decimal("4.2"),
            aave_borrow_apy=Decimal("6.1"),
        )
        result = ctx.to_prompt_context()
        assert "[Aave Market]" in result
        assert "87.5" in result

    def test_aave_section_absent_when_none(self) -> None:
        """Aave フィールドが None のとき [Aave Market] セクションは出力されない。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[Aave Market]" not in result

    def test_health_factor_section_when_set(self) -> None:
        """health_factor が設定されているとき [Health Factor] セクションが含まれる。"""
        ctx = self._ctx(health_factor=Decimal("1.72"))
        result = ctx.to_prompt_context()
        assert "[Health Factor]" in result
        assert "1.72" in result

    def test_health_factor_absent_when_none(self) -> None:
        """health_factor が None のとき [Health Factor] は出力されない。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[Health Factor]" not in result

    def test_news_section_when_available(self) -> None:
        """ニュースデータが利用可能なとき [News] セクションが含まれる。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[News]" in result
        assert "DeFi activity rises" in result
        assert "positive" in result

    def test_key_events_when_available(self) -> None:
        """key_events があるとき [Key Events] セクションが含まれる。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[Key Events]" in result
        assert "Aave V3 upgrade" in result

    def test_news_section_absent_when_no_summary(self) -> None:
        """デフォルトの "No news" サマリーのとき [News] セクションは出力されない。"""
        ctx = self._ctx(news=NewsFeedResult())  # default summary = "No news data available yet."
        result = ctx.to_prompt_context()
        assert "[News]" not in result

    def test_finance_section_when_available(self) -> None:
        """マクロデータが利用可能なとき [Macro] セクションが含まれる。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[Macro]" in result
        assert "Fed holds rates steady" in result
        assert "neutral" in result

    def test_macro_indicators_when_available(self) -> None:
        """key_indicators があるとき [Macro Indicators] が含まれる。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[Macro Indicators]" in result
        assert "CPI 3.2%" in result

    def test_finance_section_absent_when_default(self) -> None:
        """デフォルトの "No finance data" サマリーのとき [Macro] は出力されない。"""
        ctx = self._ctx(
            finance=FinanceFeedResult()
        )  # default macro_summary contains "No finance data"
        result = ctx.to_prompt_context()
        assert "[Macro]" not in result

    def test_social_sentiment_when_set(self) -> None:
        """social_sentiment_score が設定されているとき [Social Sentiment] が含まれる。"""
        ctx = self._ctx(social_sentiment_score=Decimal("72"))
        result = ctx.to_prompt_context()
        assert "[Social Sentiment]" in result
        assert "72" in result

    def test_social_sentiment_absent_when_none(self) -> None:
        """social_sentiment_score が None のとき [Social Sentiment] は出力されない。"""
        ctx = self._ctx()
        result = ctx.to_prompt_context()
        assert "[Social Sentiment]" not in result

    # ----------------------------------------------------------------
    # MMT 統合テスト
    # ----------------------------------------------------------------

    def test_mmt_section_when_data_present(self) -> None:
        """MMTData が設定されているとき to_prompt_section() の出力が統合される。"""
        mmt = _make_mmt_data(funding_rate="0.000125", oi="1500000000", oi_change_pct=2.5)
        ctx = self._ctx(mmt_data=mmt)
        result = ctx.to_prompt_context()
        assert "## MMT Market Data" in result
        assert "btc/usd" in result
        assert "Funding Rate" in result

    def test_mmt_positive_funding_rate_label(self) -> None:
        """プラスの Funding Rate は 'ロング過多' と出力される。"""
        mmt = _make_mmt_data(funding_rate="0.000100")
        ctx = self._ctx(mmt_data=mmt)
        result = ctx.to_prompt_context()
        assert "ロング過多" in result

    def test_mmt_negative_funding_rate_label(self) -> None:
        """マイナスの Funding Rate は 'ショート過多' と出力される。"""
        mmt = _make_mmt_data(funding_rate="-0.000050")
        ctx = self._ctx(mmt_data=mmt)
        result = ctx.to_prompt_context()
        assert "ショート過多" in result

    def test_mmt_oi_with_change_pct(self) -> None:
        """OI と変化率が両方出力される。"""
        mmt = _make_mmt_data(oi="2000000000", oi_change_pct=5.0)
        ctx = self._ctx(mmt_data=mmt)
        result = ctx.to_prompt_context()
        assert "OI:" in result
        assert "+5.00%" in result

    def test_mmt_section_absent_when_none(self) -> None:
        """mmt_data=None のとき MMT セクションは出力されない（既存出力に影響なし）。"""
        ctx = self._ctx(mmt_data=None)
        result = ctx.to_prompt_context()
        assert "MMT" not in result

    def test_mmt_empty_data_no_section(self) -> None:
        """MMTData が空（stats/OI なし）のとき MMT セクションは出力されない。"""
        empty_mmt = MMTData()  # stats=[], open_interest=[]
        ctx = self._ctx(mmt_data=empty_mmt)
        result = ctx.to_prompt_context()
        assert "## MMT Market Data" not in result

    def test_mmt_does_not_break_other_sections(self) -> None:
        """MMTData 追加時に既存のセクション（Geo/News/Macro）が壊れない。"""
        mmt = _make_mmt_data()
        ctx = self._ctx(mmt_data=mmt)
        result = ctx.to_prompt_context()
        # 既存セクションが維持されている
        assert "[Geopolitical Risk]" in result
        assert "[News]" in result
        assert "[Macro]" in result

    # ----------------------------------------------------------------
    # 全データなし / 最小限データ
    # ----------------------------------------------------------------

    def test_all_optional_absent_gives_minimal_output(self) -> None:
        """任意フィールドがすべて None/デフォルト → [Geopolitical Risk] のみ含む。"""
        ctx = MarketContext(
            geo_risk=_make_geo(score=50, summary="Normal"),
            news=NewsFeedResult(),  # "No news"
            finance=FinanceFeedResult(),  # "No finance data"
        )
        result = ctx.to_prompt_context()
        assert "[Geopolitical Risk]" in result
        assert "[News]" not in result
        assert "[Macro]" not in result
        assert "[Health Factor]" not in result
        assert "MMT" not in result

    def test_decimal_fields_rendered_as_string(self) -> None:
        """Decimal フィールドが正しく文字列として出力される。"""
        ctx = self._ctx(
            aave_utilization_rate=Decimal("87.123456"),
            health_factor=Decimal("1.720000"),
        )
        result = ctx.to_prompt_context()
        assert "87.123456" in result
        assert "1.720000" in result

    def test_japanese_text_in_news_is_preserved(self) -> None:
        """ニュースフィードに日本語テキストが含まれても正しく出力される。"""
        ctx = self._ctx(
            news=_make_news(
                summary="Aaveの流動性が急増している。DeFi市場は活況。",
                sentiment="positive",
                key_events=["BTCが最高値更新", "USDC安定"],
            )
        )
        result = ctx.to_prompt_context()
        assert "Aaveの流動性が急増している" in result
        assert "BTCが最高値更新" in result

    def test_output_is_newline_separated(self) -> None:
        """各セクションが改行で区切られている。"""
        ctx = self._ctx(health_factor=Decimal("1.80"))
        result = ctx.to_prompt_context()
        lines = result.split("\n")
        # 少なくとも Geo + News + Macro + HF の 4 行以上
        assert len(lines) >= 4
