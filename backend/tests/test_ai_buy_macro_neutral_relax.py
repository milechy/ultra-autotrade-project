"""A2: BUY の macro-neutral 緩和が prompt(v4/v5) に伝播され、Python ガードと整合すること。

背景 (2026-07-08):
    本番 BUY の実質ゲートは Python 側 `MultiAgentContext.indicator_and_macro_agree_bullish`
    で「fed_stance ∈ {neutral, unknown} なら Indicator BULLISH>=70 単独で成立」に緩和済み。
    しかし LLM に渡す prompt v4/v5 は「Indicator AND Macro 両方 BULLISH>=70」の AND のまま
    だったため、macro が neutral の本番では LLM 自身が HOLD を出し続け、Python ガードが
    許可していても BUY に昇格しなかった (proposals ゼロ)。本 PR で prompt に同じ緩和を伝播する。
"""

from app.ai.agents import MultiAgentContext
from app.ai.prompts import get_prompt_template


def _system(version: str) -> str:
    return get_prompt_template(version).system_prompt.lower()


def test_v4_prompt_has_macro_neutral_buy_relaxation():
    text = _system("v4")
    assert "fed_stance" in text
    assert "neutral" in text and "unknown" in text
    # BUY 単独許可の明示
    assert "buy" in text and "alone" in text


def test_v5_prompt_has_macro_neutral_buy_relaxation():
    text = _system("v5")
    assert "fed_stance" in text
    assert "neutral" in text and "unknown" in text
    assert "buy" in text and "alone" in text


def test_relaxation_is_buy_only_not_sell():
    """緩和は BUY のみ・SELL には適用しないことが prompt に明記されていること (#365 SELL-spam 防止)。"""
    for version in ("v4", "v5"):
        text = _system(version)
        # SELL は緩和対象外である旨 (never/only を BUY 文脈で明示)
        assert "never" in text or "only" in text


def test_prompt_relaxation_matches_python_guard_fed_stances():
    """prompt に書いた緩和対象 fed_stance が Python ガードの _BULLISH_RELAX_FED_STANCES と一致。

    片方だけ変更されて prompt と rule engine が乖離する drift を防ぐ。
    """
    # Pydantic private 属性はクラス経由だと descriptor が返るためインスタンス経由で読む。
    guard_stances = MultiAgentContext()._BULLISH_RELAX_FED_STANCES
    assert guard_stances == frozenset({"neutral", "unknown"})
    for version in ("v4", "v5"):
        text = _system(version)
        for stance in guard_stances:
            assert stance in text, f"{version} prompt missing fed_stance '{stance}'"
