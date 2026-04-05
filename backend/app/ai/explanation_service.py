# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ExplanationContext(BaseModel):
    action: str  # BUY, SELL, HOLD, SUPPLY, WITHDRAW
    utilization_rate: Decimal  # 0.0 - 1.0
    supply_apy: Decimal
    volatility_30d: Decimal  # 0.0 - 1.0
    impact_with: Decimal  # expected gain/loss if executed (USD)
    impact_without: Decimal  # expected gain/loss if not executed (USD)
    impact_difference: Decimal  # impact_with - impact_without
    asset_symbol: str


class FiveStepExplanation(BaseModel):
    conclusion: str
    reason: str
    impact: str
    risks: list[str]
    comparison: str


class SignalDisplay(BaseModel):
    icon: str
    label_ja: str
    label_en: str
    description_ja: str
    weather: Literal["sunny", "cloudy", "stormy"]


class ExplanationService:
    """テンプレートベースの5ステップ説明生成サービス。LLM不要。"""

    def generate(self, context: ExplanationContext) -> FiveStepExplanation:
        return FiveStepExplanation(
            conclusion=self._conclusion(context),
            reason=self._reason(context),
            impact=self._impact(context),
            risks=self._risks(context),
            comparison=self._comparison(context),
        )

    def generate_signal(self, context: ExplanationContext) -> SignalDisplay:
        util = float(context.utilization_rate)
        vol = float(context.volatility_30d)
        action = context.action.upper()

        if action in ("SELL", "WITHDRAW"):
            return SignalDisplay(
                icon="🌪️",
                label_ja="荒天",
                label_en="stormy",
                description_ja="資産を引き出すタイミングです。慎重に判断してください。",
                weather="stormy",
            )

        if util > 0.95 or vol > 0.10:
            return SignalDisplay(
                icon="🌪️",
                label_ja="荒天",
                label_en="stormy",
                description_ja="市場が不安定です。リスクが高い状態です。",
                weather="stormy",
            )

        if 0.80 <= util <= 0.95 and vol < 0.05:
            return SignalDisplay(
                icon="☀️",
                label_ja="晴れ",
                label_en="sunny",
                description_ja="借りる人が多く利息が高め。預けるのに良い状態です。",
                weather="sunny",
            )

        return SignalDisplay(
            icon="☁️",
            label_ja="曇り",
            label_en="cloudy",
            description_ja="普通の状態です。状況を見ながら判断しましょう。",
            weather="cloudy",
        )

    # ── private helpers ──────────────────────────────────────────────────────

    def _conclusion(self, ctx: ExplanationContext) -> str:
        action = ctx.action.upper()
        symbol = ctx.asset_symbol
        if action in ("BUY", "SUPPLY"):
            return f"{symbol}を預けることをおすすめします。"
        if action in ("SELL", "WITHDRAW"):
            return f"{symbol}を引き出すことをおすすめします。"
        return f"{symbol}については様子を見ることをおすすめします。"

    def _reason(self, ctx: ExplanationContext) -> str:
        util = float(ctx.utilization_rate)
        vol = float(ctx.volatility_30d)
        parts: list[str] = []

        if util >= 0.80:
            parts.append("現在、借りる人が多い状態です。そのため利息が高くなっています。")
        elif util < 0.50:
            parts.append("現在、借りる人が少ない状態です。利息はやや低めです。")
        else:
            parts.append("借りる人の多さは普通の水準です。")

        if vol > 0.10:
            parts.append("価格の動きが激しく、不安定な状態です。")
        elif vol > 0.05:
            parts.append("価格がやや不安定です。")
        else:
            parts.append("価格は比較的安定しています。")

        return "".join(parts)

    def _impact(self, ctx: ExplanationContext) -> str:
        with_val = ctx.impact_with
        without_val = ctx.impact_without
        sign_with = "+" if with_val >= 0 else ""
        sign_without = "+" if without_val >= 0 else ""
        return (
            f"実行した場合の見込み: {sign_with}{with_val:.2f} USD。"
            f"実行しない場合の見込み: {sign_without}{without_val:.2f} USD。"
        )

    def _risks(self, ctx: ExplanationContext) -> list[str]:
        risks: list[str] = []
        vol = float(ctx.volatility_30d)
        util = float(ctx.utilization_rate)

        if vol > 0.10:
            risks.append("価格が大きく変動する可能性があります。")
        elif vol > 0.05:
            risks.append("価格が多少変動する可能性があります。")

        if util > 0.95:
            risks.append("借りる人が非常に多く、急に利息が上がることがあります。")
        elif util > 0.80:
            risks.append("借りる人が多いため、利息が変わりやすい状態です。")

        if not risks:
            risks.append("現時点で特に大きなリスクは見当たりません。")

        return risks

    def _comparison(self, ctx: ExplanationContext) -> str:
        diff = ctx.impact_difference
        sign = "+" if diff >= 0 else ""
        if diff > 0:
            return f"実行することで、しない場合より {sign}{diff:.2f} USD 多く得られる見込みです。"
        if diff < 0:
            return f"実行すると、しない場合より {abs(diff):.2f} USD 少なくなる見込みです。"
        return "実行してもしなくても、見込みの差はほぼありません。"
