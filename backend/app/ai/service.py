# backend/app/ai/service.py
"""
AI 解析ロジックのサービス層。

責務:
- NotionNewsItem を入力として BUY / SELL / HOLD を決定する
- docs/05_ai_judgement_rules.md のルールを満たす範囲で判定する
- 外部の LLM クライアント（OpenAI 等）を差し替え可能な構造にする
- エラー時・異常値時は HOLD 優先で安全側に倒す
"""

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional

from app.notion.schemas import NotionNewsItem

from .config import AISettings, get_ai_settings
from .schemas import (
    AIAnalysisResult,
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    RAGContext,
    TradeAction,
)

logger = logging.getLogger(__name__)


# LLM クライアントの型（NotionNewsItem -> AIAnalysisResult を返す callable を想定）
LLMAnalyzer = Callable[[NotionNewsItem], AIAnalysisResult]


# docs/05_ai_judgement_rules.md を踏まえたガイドラインとなる説明文。
# 実際の LLM プロンプトとして利用する場合は、この定数をベースに system / user プロンプトを組み立てる想定。
LLM_SYSTEM_PROMPT = """
あなたは暗号資産の自動運用システム Ultra AutoTrade の AI 判定モジュールです。

入力として 1 件のニュース（タイトル・サマリ・URL など）が与えられます。
あなたの役割は、そのニュースが「市場に対してポジティブか / ネガティブか / 中立か」を判断し、
以下の情報を JSON 形式で返すことです。

- action: "BUY" / "SELL" / "HOLD" のいずれか
- confidence: 0〜100 の整数（80以上はかなり自信あり）
- sentiment: "positive" / "negative" / "neutral" などの短い文字列
- summary: ニュースの要約（日本語、最大 200 文字程度）
- reason: なぜそのアクションになったのかの説明（日本語、最大 200 文字程度）

重要な制約:
- docs/05_ai_judgement_rules.md に基づき、過剰な売買は避け、迷ったら HOLD を選ぶ
- confidence < 40 の場合は基本的に HOLD を推奨する
- BUY/SELL を返すのは「強いポジティブ/ネガティブニュース」で、整合性も取れている場合のみ
"""


class AIService:
    """
    ニュース一覧を受け取り、AI 判定結果一覧を返すサービスクラス。

    - コンストラクタで LLMAnalyzer を注入可能（テストではモックを渡す）
    - デフォルトでは簡易なキーワードベースのルールで判定を行う
    """

    def __init__(self, *, llm_analyzer: Optional[LLMAnalyzer] = None) -> None:
        self._llm_analyzer = llm_analyzer

    def analyze_items(self, items: Iterable[NotionNewsItem]) -> List[AIAnalysisResult]:
        """
        NotionNewsItem の反復可能オブジェクトを受け取り、AIAnalysisResult のリストを返す。
        """
        results: List[AIAnalysisResult] = []
        now = datetime.now(timezone.utc)

        for item in items:
            result = self._analyze_single(item, now)
            results.append(result)

        return results

    def _analyze_single(
        self,
        item: NotionNewsItem,
        now: Optional[datetime] = None,
    ) -> AIAnalysisResult:
        """
        1件のニュースに対する判定を行う。

        1. LLMAnalyzer が設定されていればそれを優先して利用
        2. 例外発生 / 異常値の場合はログを残して HOLD にフォールバック
        3. LLMAnalyzer が無い場合は簡易ルールベース判定を実施
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # まずは LLMAnalyzer があればそれを試す
        if self._llm_analyzer is not None:
            try:
                llm_result = self._llm_analyzer(item)
                safe_result = self._apply_safety_guards(llm_result)
                return safe_result
            except Exception as exc:  # noqa: BLE001
                # セキュリティ設計に基づき、ニュース本文などはログに直接書かず、
                # ID や URL などの最低限の情報だけを記録する。
                logger.warning(
                    "LLM analyzer failed; fallback to rule-based decision. id=%s url=%s error=%s",
                    getattr(item, "id", "unknown"),
                    getattr(item, "url", "unknown"),
                    exc,
                )

        # LLM を使わない / 使えない場合は簡易ルールベース
        rule_based = self._rule_based_decision(item, now)
        safe_result = self._apply_safety_guards(rule_based)
        return safe_result

    def _apply_safety_guards(self, result: AIAnalysisResult) -> AIAnalysisResult:
        """
        docs/05_ai_judgement_rules.md の「安全弁」に基づき、
        confidence が低すぎる場合や不正値の場合は HOLD に寄せる。
        """
        # 不正な信頼度は補正
        confidence = result.confidence
        if confidence < 0:
            confidence = 0
        if confidence > 100:
            confidence = 100

        action = result.action

        # 信頼度が 40 未満の場合は SELL/BUY は避け、HOLD にする
        if confidence < 40 or action not in (TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD):
            action = TradeAction.HOLD

        # 修正した値を反映した新しいインスタンスを返す（元オブジェクトは変更しない）
        return AIAnalysisResult(
            id=result.id,
            url=result.url,
            action=action,
            confidence=confidence,
            sentiment=result.sentiment,
            summary=result.summary,
            reason=result.reason,
            timestamp=result.timestamp,
        )

    def _rule_based_decision(
        self,
        item: NotionNewsItem,
        now: Optional[datetime] = None,
    ) -> AIAnalysisResult:
        """
        非LLM環境でも動作する簡易なキーワードベース判定。

        - 非常にラフなロジックだが、Phase2 のたたき台として実装
        - 本番運用では LLMAnalyzer による判定に徐々に置き換える前提
        """
        if now is None:
            now = datetime.now(timezone.utc)

        text = " ".join(
            part
            for part in [
                getattr(item, "summary", None),
                getattr(item, "url", None),
            ]
            if part
        ).lower()

        # ごく簡単なキーワードリスト
        positive_keywords = [
            "record profit",
            "record revenue",
            "profit grows",
            "bullish",
            "upgrade",
            "上方修正",
            "好調",
            "増益",
            "最高益",
            "成長",
        ]
        negative_keywords = [
            "fraud",
            "scandal",
            "bankruptcy",
            "lawsuit",
            "downgrade",
            "暴落",
            "下方修正",
            "不祥事",
            "破綻",
            "赤字",
        ]

        sentiment = "neutral"
        action = TradeAction.HOLD
        confidence = 50
        reason = "ニュース内容が中立または判断が難しいため、HOLD としました。"

        if any(keyword in text for keyword in positive_keywords):
            sentiment = "positive"
            action = TradeAction.BUY
            confidence = 80
            reason = "好材料が多く、市場にポジティブな影響が見込まれるため BUY 判定としました。"
        elif any(keyword in text for keyword in negative_keywords):
            sentiment = "negative"
            action = TradeAction.SELL
            confidence = 80
            reason = "悪材料が多く、市場にネガティブな影響が見込まれるため SELL 判定としました。"

        return AIAnalysisResult(
            id=getattr(item, "id", ""),
            url=getattr(item, "url", ""),
            action=action,
            confidence=confidence,
            sentiment=sentiment,
            summary=getattr(item, "summary", None),
            reason=reason,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Two-Phase AI Judge with RAG（Step 4 追加分）
    # ------------------------------------------------------------------

    def judge_with_rag(
        self,
        query: str,
        rag_context: RAGContext,
        *,
        settings: Optional[AISettings] = None,
    ) -> CrossValidationResult:
        """
        Two-phase AI judge with RAG context.
        Phase 1: Claude (primary)
        Phase 2: GPT-4o (secondary, cross-validation)
        """
        ai_settings = settings or get_ai_settings()
        prompt = self._build_rag_prompt(query, rag_context)

        # Phase 1: Primary (Claude)
        primary = self._call_claude(prompt, ai_settings)

        # Phase 2: Secondary (OpenAI) - only if enabled and key available
        secondary = None
        if ai_settings.cross_validation_enabled and ai_settings.openai_api_key:
            secondary = self._call_openai(prompt, ai_settings)

        return self._cross_validate(primary, secondary)

    def _build_rag_prompt(self, query: str, rag_context: RAGContext) -> str:
        """Build prompt with RAG context chunks."""
        chunks_text = (
            "\n---\n".join(rag_context.chunks)
            if rag_context.chunks
            else "(No relevant context found)"
        )
        return f"""{LLM_SYSTEM_PROMPT}

## Retrieved Context (from Knowledge Hub):
{chunks_text}

## Analysis Request:
{query}

Respond in JSON format only: {{"action": "BUY"|"SELL"|"HOLD", "confidence": 0-100, "reason": "..."}}"""

    def _call_claude(self, prompt: str, settings: AISettings) -> LLMDecision:
        """Call Claude API. Fail-closed: error→HOLD."""
        if not settings.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set; falling back to HOLD")
            return LLMDecision(
                provider=LLMProvider.CLAUDE,
                action=TradeAction.HOLD,
                confidence=0,
                reason="API key not configured",
            )
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.claude_model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_llm_response(response.content[0].text, LLMProvider.CLAUDE)
        except Exception as exc:
            logger.error("Claude API call failed: %s", exc)
            return LLMDecision(
                provider=LLMProvider.CLAUDE,
                action=TradeAction.HOLD,
                confidence=0,
                reason=f"API error: {exc}",
            )

    def _call_openai(self, prompt: str, settings: AISettings) -> LLMDecision:
        """Call OpenAI API. Fail-closed: error→HOLD."""
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not set; falling back to HOLD")
            return LLMDecision(
                provider=LLMProvider.OPENAI,
                action=TradeAction.HOLD,
                confidence=0,
                reason="API key not configured",
            )
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            return self._parse_llm_response(response.choices[0].message.content, LLMProvider.OPENAI)
        except Exception as exc:
            logger.error("OpenAI API call failed: %s", exc)
            return LLMDecision(
                provider=LLMProvider.OPENAI,
                action=TradeAction.HOLD,
                confidence=0,
                reason=f"API error: {exc}",
            )

    def _parse_llm_response(self, raw: str, provider: LLMProvider) -> LLMDecision:
        """Parse JSON response from LLM. Parse failure→HOLD."""
        try:
            text = raw.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
            action_str = data.get("action", "HOLD").upper()
            if action_str not in ("BUY", "SELL", "HOLD"):
                action_str = "HOLD"
            action = TradeAction(action_str)
            confidence = max(0, min(100, int(data.get("confidence", 0))))
            reason = data.get("reason", "")
            return LLMDecision(
                provider=provider,
                action=action,
                confidence=confidence,
                reason=reason,
                raw_response=raw,
            )
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse LLM response from %s: %s", provider.value, exc)
            return LLMDecision(
                provider=provider,
                action=TradeAction.HOLD,
                confidence=0,
                reason=f"Parse error: {exc}",
                raw_response=raw,
            )

    def _cross_validate(
        self, primary: LLMDecision, secondary: Optional[LLMDecision]
    ) -> CrossValidationResult:
        """
        Cross-validation logic:
        - No secondary → use primary
        - Both agree → average confidence
        - Disagree → HOLD (fail-closed)
        """
        if secondary is None:
            return CrossValidationResult(
                primary=primary,
                secondary=None,
                agreed=True,
                final_action=primary.action,
                final_confidence=primary.confidence,
                final_reason=primary.reason,
            )

        agreed = primary.action == secondary.action
        if agreed:
            avg_confidence = (primary.confidence + secondary.confidence) // 2
            return CrossValidationResult(
                primary=primary,
                secondary=secondary,
                agreed=True,
                final_action=primary.action,
                final_confidence=avg_confidence,
                final_reason=f"Both LLMs agree: {primary.reason}",
            )
        else:
            min_confidence = min(primary.confidence, secondary.confidence)
            return CrossValidationResult(
                primary=primary,
                secondary=secondary,
                agreed=False,
                final_action=TradeAction.HOLD,
                final_confidence=min(min_confidence, 30),
                final_reason=f"LLMs disagree ({primary.action.value} vs {secondary.action.value}); defaulting to HOLD",
            )
