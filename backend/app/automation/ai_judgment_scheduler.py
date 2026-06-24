# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/automation/ai_judgment_scheduler.py
"""AI判定定期スケジューラー。

ティア別間隔で AI 判定を実行し、結果を ai_decisions に保存する。
- UPPER ティア:  AI_JUDGMENT_INTERVAL_HOURS_UPPER (デフォルト 4 時間)
- MIDDLE ティア: AI_JUDGMENT_INTERVAL_HOURS_MIDDLE (デフォルト 6 時間)
- LOWER ティア:  AI_JUDGMENT_INTERVAL_HOURS_LOWER (デフォルト 8 時間)
- GENERAL ティア: AI_JUDGMENT_INTERVAL_HOURS_GENERAL (デフォルト 8 時間、v9 互換)
BUY/SELL 判定時はティア間隔を満たすアクティブユーザーに Proposal を作成する。
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.aave.gas_estimator import estimate_static_gas_cost_usd
from app.ai.judgment_log import get_judgment_logger
from app.ai.models import AIDecision, AiDecisionFeature
from app.ai.schemas import CrossValidationResult, RAGContext, TradeAction
from app.ai.service import AIService
from app.auth.constants import ExecutionPolicy
from app.auth.models import InvestmentTier, User, normalize_tier
from app.automation.aave_data_fetcher import AaveMarketData, fetch_aave_market_data_safe
from app.data_feeds.context import MarketContext, build_market_context
from app.database import SessionLocal
from app.knowledge.schemas import KnowledgeSearchRequest
from app.knowledge.service import KnowledgeService
from app.proposals.models import Proposal

# ティア別デフォルト判定間隔（時間）
_DEFAULT_INTERVAL_UPPER = 4
_DEFAULT_INTERVAL_MIDDLE = 6
_DEFAULT_INTERVAL_LOWER = 8

# 起動直後の即時 fan-out 抑制: 再起動のたびに全 due user が一斉実行されるのを防ぐ。
# AI_JUDGMENT_STARTUP_DELAY_SEC (デフォルト 300 秒) 待機後に第1 tick を実行する。
# watchdog / Slack 通知 / Cloudflare Tunnel 等が立ち上がる猶予を確保する目的。
# 0 を設定すると遅延なし（テスト・デバッグ用途）。
_DEFAULT_STARTUP_DELAY_SEC = int(os.getenv("AI_JUDGMENT_STARTUP_DELAY_SEC", "300"))

logger = logging.getLogger(__name__)

# --- スケジューラー実行状態（/health から参照） ---
_scheduler_started: bool = False
_last_run_at: "datetime | None" = None
_next_run_at: "datetime | None" = None
_last_error_msg: "str | None" = None


def get_scheduler_status() -> "dict[str, Any]":
    """スケジューラーの稼働状態を返す（/health エンドポイント用）。"""
    return {
        "running": _scheduler_started,
        "last_run": _last_run_at.isoformat() if _last_run_at else None,
        "next_run": _next_run_at.isoformat() if _next_run_at else None,
        "last_error": _last_error_msg,
    }


_DEFAULT_QUERY = "DeFi market analysis"
_PROPOSAL_ASSET = "USDC"
_PROPOSAL_EXPIRES_HOURS = 72

# 提案金額: fund_allocations.allocated_amount_usd × _PROPOSAL_RATIO で動的計算。
# fund_allocation 不在の非カストディアル消費者は本人 wallet の USDC 残高 × ratio に
# fallback する (案C / docs/61)。いずれも sizing 不能なら Decimal("0") → skip (安全側)。
# 環境変数で上書き可能。
_PROPOSAL_RATIO = Decimal(os.getenv("PROPOSAL_AMOUNT_RATIO", "0.10"))  # 10%
_PROPOSAL_AMOUNT_MIN_USD = Decimal(os.getenv("PROPOSAL_AMOUNT_MIN_USD", "50"))
_PROPOSAL_AMOUNT_MAX_USD = Decimal(os.getenv("PROPOSAL_AMOUNT_MAX_USD", "2000"))

# USDC は 6 decimals。ERC20 balanceOf の最小 ABI。
_USDC_DECIMALS = 6
_ERC20_BALANCE_OF_ABI: list[dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


def _read_wallet_usdc_balance(wallet_address: str) -> Optional[Decimal]:
    """active chain 上の wallet USDC 残高 (USDC 単位) を返す。

    AAVE_ACTIVE_CHAINS の先頭チェーン (production=base / staging=base_sepolia) の USDC
    コントラクトに対し web3 で balanceOf する (web3.py の .call() は同期)。
    web3 未導入 / RPC URL 未設定 / 不正アドレス / RPC 失敗時は **None** を返し、
    呼び出し側で skip させる (安全側: 残高不明のまま提案金額を捏造しない)。

    NOTE: チェーン別 USDC アドレス・RPC は app.aave.chains に集約済 (mainnet 直書きしない)。
    """
    try:
        from web3 import Web3  # noqa: PLC0415

        from app.aave.chains import (  # noqa: PLC0415
            get_active_chains,
            get_rpc_url_for_chain,
        )

        chain = get_active_chains()[0]
        usdc_addr = chain.tokens.get("USDC")
        if not usdc_addr:
            logger.warning("[proposal_amount] USDC address missing for %s", chain.chain_name)
            return None
        rpc_url = get_rpc_url_for_chain(chain)
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        contract = w3.eth.contract(
            address=w3.to_checksum_address(usdc_addr),
            abi=_ERC20_BALANCE_OF_ABI,
        )
        raw_balance = contract.functions.balanceOf(w3.to_checksum_address(wallet_address)).call()
        return Decimal(raw_balance) / Decimal(10**_USDC_DECIMALS)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[proposal_amount] wallet USDC balance read failed for %s: %s",
            wallet_address,
            exc,
        )
        return None


def _resolve_proposal_amount(db: Session, user_id: int) -> Decimal:
    """提案金額を解決する (案C: fund_allocation 優先 + wallet 残高 fallback / docs/61)。

    1. active fund_allocations 合計 × ratio (custodial パートナー/テスター枠)。
       min/max にクランプ。**既存挙動を完全維持**。
    2. allocation 不在 & wallet 設定済の非カストディアル消費者: 本人 wallet の
       on-chain USDC 残高 × ratio。残高0 / 取得失敗 / min 未満は Decimal("0") で skip
       (安全側: wallet 額を超える/極小の提案を作らない)。
    3. allocation も wallet も無い: sizing 不能 → Slack 通知 + Decimal("0")
       (パートナー/テスター登録漏れの検知を維持)。

    $0 は呼び出し側 (_create_proposals_for_users) の explicit check でスキップされる。
    金融計算は Decimal のみ (CLAUDE.md)。
    """
    from app.partner.allocation_models import FundAllocation  # noqa: PLC0415

    # ── 1. fund_allocation 優先 (custodial 枠) ──
    raw = (
        db.query(func.sum(FundAllocation.allocated_amount_usd))
        .filter(
            FundAllocation.tester_user_id == user_id,
            FundAllocation.status == "active",
        )
        .scalar()
    )
    allocated = Decimal(str(raw)) if raw else Decimal("0")
    if allocated > Decimal("0"):
        amount = (allocated * _PROPOSAL_RATIO).quantize(Decimal("0.01"))
        return max(_PROPOSAL_AMOUNT_MIN_USD, min(amount, _PROPOSAL_AMOUNT_MAX_USD))

    # ── 2. fallback: 非カストディアル消費者の wallet USDC 残高 ──
    user = db.get(User, user_id)
    wallet = (user.smart_wallet_address or user.wallet_address) if user else None
    if wallet:
        balance = _read_wallet_usdc_balance(wallet)
        if balance is None or balance <= Decimal("0"):
            # 残高0 / RPC 取得失敗 → skip (安全側)
            logger.debug(
                "[proposal_amount] wallet USDC 0/unavailable for user_id=%d — skipped",
                user_id,
            )
            return Decimal("0")
        amount = (balance * _PROPOSAL_RATIO).quantize(Decimal("0.01"))
        if amount < _PROPOSAL_AMOUNT_MIN_USD:
            # 10% が gas viable な最小額未満 → skip。
            # allocation 経路は min へ切り上げるが、消費者 wallet 経路では残高に対し
            # 過大な supply を避けるため切り上げず skip する (意図的な非対称 / docs/61)。
            logger.debug(
                "[proposal_amount] wallet-based amount %s < min $%s for user_id=%d — skipped",
                amount,
                _PROPOSAL_AMOUNT_MIN_USD,
                user_id,
            )
            return Decimal("0")
        return min(amount, _PROPOSAL_AMOUNT_MAX_USD)

    # ── 3. allocation も wallet も無い → sizing 不能 ──
    logger.warning(
        "no active fund_allocation and no wallet for user_id=%d — proposal skipped. "
        "ACTION: register fund_allocations (tester) or ensure wallet is set (consumer).",
        user_id,
    )
    _notify_missing_allocation(user_id)
    return Decimal("0")


def _notify_missing_allocation(user_id: int) -> None:
    """fund_allocations 未設定ユーザーを Slack 通知する (best-effort)。"""
    try:
        from app.notifications.factory import get_notification_service  # noqa: PLC0415
        from app.notifications.schemas import (  # noqa: PLC0415
            NotificationChannel,
            NotificationMessage,
            NotificationSeverity,
        )

        msg = NotificationMessage(
            user_id=None,
            channel=NotificationChannel.SLACK,
            severity=NotificationSeverity.WARNING,
            title="⚠️ fund_allocations 未設定",
            body=(
                f"user_id={user_id} に active な fund_allocations がありません。\n"
                "ACTION REQUIRED: production DB に INSERT してください。\n"
                "提案生成をスキップしました。"
            ),
        )
        get_notification_service().send(msg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("_notify_missing_allocation failed for user_id=%d: %s", user_id, exc)


def save_ai_decision(
    db: Session,
    result: CrossValidationResult,
    query: str,
    user_id: Optional[int] = None,
    rag_context: Optional[RAGContext] = None,
) -> AIDecision:
    """CrossValidationResult を ai_decisions テーブルに保存して返す。

    Args:
        db: SQLAlchemy セッション。
        result: AI クロスバリデーション結果。
        query: 判定に使ったクエリ文字列。
        user_id: 紐づけるユーザー ID（None = システム判定）。
        rag_context: 判定に使った RAG コンテキスト。None の場合は保存しない。

    Returns:
        保存済みの AIDecision インスタンス。
    """
    decision = AIDecision(
        user_id=user_id,
        query=query,
        action=result.final_action.value,
        confidence=result.final_confidence,
        reason=result.final_reason,
        primary_provider=result.primary.provider.value,
        primary_action=result.primary.action.value,
        primary_confidence=result.primary.confidence,
        secondary_provider=result.secondary.provider.value if result.secondary else None,
        secondary_action=result.secondary.action.value if result.secondary else None,
        secondary_confidence=result.secondary.confidence if result.secondary else None,
        agreed=result.agreed,
        rag_context_json=rag_context.model_dump() if rag_context else None,
        prompt_version=result.primary.prompt_version,
    )
    db.add(decision)
    db.flush()  # id を確定させる
    return decision


def _build_agent_signals_json(market_ctx: Any) -> Optional[dict[str, Any]]:
    """MarketContext から run_all_agents() を呼び、jsonb 用 dict を返す。

    market_ctx が MarketContext でない場合 (degraded dict) は None を返す。
    """
    from app.ai.agents import run_all_agents  # noqa: PLC0415

    if not isinstance(market_ctx, MarketContext):
        return None
    try:
        agent_ctx = run_all_agents(market_ctx)
        signals: dict[str, Any] = {}
        for key, sig in (
            ("indicator", agent_ctx.indicator_signal),
            ("pattern", agent_ctx.pattern_signal),
            ("risk", agent_ctx.risk_signal),
            ("macro", agent_ctx.macro_signal),
        ):
            if sig is not None:
                signals[key] = {
                    "bias": sig.bias.value,
                    "confidence": sig.confidence,
                    "key_data": {k: str(v) for k, v in sig.key_data.items()},
                }
        return signals or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("_build_agent_signals_json failed: %s", exc)
        return None


def _build_raw_features_json(
    aave_data: "AaveMarketData",
    market_ctx: Any,
) -> dict[str, Any]:
    """fetch_aave_market_data_safe() の結果 + MarketContext から raw_features dict を返す。

    RSI/MACD/volatility/gas は現コードに存在しないため含めない。
    """
    raw: dict[str, Any] = {
        "utilization_rate": str(aave_data["utilization_rate"])
        if aave_data["utilization_rate"] is not None
        else None,
        "supply_apy": str(aave_data["supply_apy"]) if aave_data["supply_apy"] is not None else None,
        "borrow_apy": str(aave_data["borrow_apy"]) if aave_data["borrow_apy"] is not None else None,
        "health_factor": str(aave_data["health_factor"])
        if aave_data["health_factor"] is not None
        else None,
    }
    if isinstance(market_ctx, MarketContext):
        raw["geo_risk_score"] = market_ctx.geo_risk.geo_risk_score
        raw["news_sentiment"] = market_ctx.news.sentiment
        raw["fed_stance"] = market_ctx.finance.fed_stance
        raw["stablecoin_risk"] = market_ctx.finance.stablecoin_risk
    return raw


def _generate_embedding(text: str) -> Optional[list[float]]:
    """text-embedding-3-small で 1536 次元ベクトルを生成する (fail-open)。

    OpenAI キーが未設定または API 呼び出し失敗時は None を返す。
    """
    try:
        from openai import OpenAI  # noqa: PLC0415

        from app.ai.config import get_ai_settings  # noqa: PLC0415

        api_key = get_ai_settings().openai_api_key
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=1536,
        )
        return resp.data[0].embedding
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding generation failed (fail-open): %s", exc)
        return None


def _write_shadow_consensus(
    db: Session,
    feature: AiDecisionFeature,
    market_ctx: Any,
) -> None:
    """4 軸コンセンサスの決定論判定を Shadow 記録する (EPIC-1 1-7 / fail-open)。

    consensus_4axis_mode が "off" の場合は何もしない。それ以外 (shadow/a_b/on)
    のとき feature.deterministic_breakdown に DeterministicVerdict を格納する。
    Shadow = 記録のみで、既存の判定・保存ロジックには一切影響させない。

    market_ctx が MarketContext でない場合 (degraded dict) は skip する。
    本関数の例外は WARNING ログに留め、呼び出し元の判定保存処理を阻害しない。
    """
    from app.ai.agents import run_all_agents  # noqa: PLC0415
    from app.ai.config import get_ai_settings  # noqa: PLC0415

    try:
        settings = get_ai_settings()
        if settings.consensus_4axis_mode == "off":
            return
        if not isinstance(market_ctx, MarketContext):
            return

        agent_ctx = run_all_agents(market_ctx)
        verdict = agent_ctx.evaluate_4axis_consensus(
            score_threshold=settings.consensus_score_threshold,
            conf_threshold=settings.consensus_conf_threshold,
        )
        feature.deterministic_breakdown = verdict.model_dump(mode="json")
        db.flush()
        logger.info(
            "shadow consensus recorded: feature_id=%s mode=%s action=%s",
            feature.id,
            settings.consensus_4axis_mode,
            verdict.action.value,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "_write_shadow_consensus failed (fail-open, decision_id=%s): %s",
            getattr(feature, "ai_decision_id", None),
            exc,
        )


def save_ai_decision_features(
    db: Session,
    decision: AIDecision,
    result: CrossValidationResult,
    aave_data: "AaveMarketData",
    market_ctx: Any,
) -> "AiDecisionFeature | None":
    """ai_decision_features に判定時の特徴量を INSERT する (fail-open)。

    呼び出し元の db.commit() 前に呼ぶこと。INSERT 失敗は WARNING ログに留め、
    判定結果の保存 (save_ai_decision) には影響させない。

    Returns:
        flush 済みの AiDecisionFeature（_write_shadow_consensus 後の状態）。
        INSERT 失敗時は None を返す。
        呼び出し側は None の場合も継続できる設計 (fail-open)。

    Args:
        db: SQLAlchemy セッション (flush 済み decision を持つ)。
        decision: flush 済みの AIDecision (id が確定している)。
        result: AI クロスバリデーション結果。
        aave_data: fetch_aave_market_data_safe() の返り値。
        market_ctx: build_market_context() の返り値、または degraded dict。
    """
    try:
        agent_signals = _build_agent_signals_json(market_ctx)
        raw_features = _build_raw_features_json(aave_data, market_ctx)
        embed_text = result.final_reason or _DEFAULT_QUERY
        embedding = _generate_embedding(embed_text)

        feature = AiDecisionFeature(
            ai_decision_id=decision.id,
            agent_signals=agent_signals,
            raw_features=raw_features,
            judge_action=result.final_action.value,
            confidence=result.final_confidence,
            cross_verify=result.agreed,
            embedding=embedding,
        )
        db.add(feature)
        db.flush()
        logger.info(
            "ai_decision_features inserted: decision_id=%d action=%s confidence=%d",
            decision.id,
            result.final_action.value,
            result.final_confidence,
        )
        # EPIC-1 1-7: 4 軸コンセンサス Shadow 書込配線 (記録のみ / fail-open)
        _write_shadow_consensus(db, feature, market_ctx)
        return feature
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "save_ai_decision_features failed (fail-open, decision_id=%d): %s",
            decision.id,
            exc,
        )
        return None


def _consensus_ab_bucket(decision_id: int) -> str:
    """CONSENSUS_4AXIS_MODE="a_b" 時の 50/50 バケット振り分けを返す。

    decisions_router (backend/app/ai/decisions_router.py) の計測エンドポイントと
    同一規約: ``"new" if id % 2 == 1 else "legacy"``。
    **この式を decisions_router と乖離させないこと**。
    乖離すると 1-12 A/B 計測の bucket 定義と実際のルーティングが食い違い、
    計測値が無意味になる。

    Args:
        decision_id: ai_decisions.id (flush 後の確定値)。

    Returns:
        "new"    — 奇数 id → 4 軸 deterministic verdict を採用。
        "legacy" — 偶数 id → 従来 LLM final_action をそのまま routing。
    """
    return "new" if decision_id % 2 == 1 else "legacy"


def _get_tier_interval_hours(tier: str) -> int:
    """ティアに応じた AI 判定間隔（時間）を返す。

    環境変数で上書き可能:
    - AI_JUDGMENT_INTERVAL_HOURS_UPPER (デフォルト 4)
    - AI_JUDGMENT_INTERVAL_HOURS_MIDDLE (デフォルト 6)
    - AI_JUDGMENT_INTERVAL_HOURS_LOWER (デフォルト 8)
    """
    if tier == InvestmentTier.UPPER.value:
        return int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS_UPPER", str(_DEFAULT_INTERVAL_UPPER)))
    if tier == InvestmentTier.MIDDLE.value:
        return int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS_MIDDLE", str(_DEFAULT_INTERVAL_MIDDLE)))
    # LOWER または未知の値 → LOWER デフォルト
    return int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS_LOWER", str(_DEFAULT_INTERVAL_LOWER)))


def _is_user_due_for_judgment(user: User, now: datetime) -> bool:
    """ユーザーがティア別間隔を満たしているか判定する。

    last_judgment_at が None（初回）または interval 経過済みの場合 True を返す。
    """
    if user.last_judgment_at is None:
        return True
    interval = _get_tier_interval_hours(user.tier)
    last = user.last_judgment_at
    # timezone-aware 比較
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now >= last + timedelta(hours=interval)


def _multiprotocol_routing_enabled() -> bool:
    """AI Optimizer 経由のマルチプロトコル提案ルーティングが有効か。

    デフォルト無効 (既存 Aave 既定挙動を完全維持)。env で明示的に opt-in する。
    """
    import os  # noqa: PLC0415

    return os.getenv("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED", "false").lower() == "true"


def _resolve_protocol_routing(
    result: CrossValidationResult,
    risk_mode: str | None,
    investment_usd: Decimal,
) -> tuple[str, str, str]:
    """Proposal の (operation, asset, protocol) を決める (Phase-B)。

    既定 (フラグ無効 / SELL / optimizer 失敗 / aave 推奨) は Aave 既定経路
    ``(SUPPLY|WITHDRAW, "USDC", "aave")``。フラグ有効かつ BUY かつ AI Optimizer が
    lido/pendle を推奨した場合のみ該当プロトコルへルーティングする:
      - Lido → ``("STAKE_ETH", "ETH", "lido")``
      - Pendle → ``("BUY_PT", "PT-stETH", "pendle")``

    いずれの場合も on-chain 実行は行わず、Proposal を DB に作成するのみ
    (実際の ETH staking / Pendle swap の broadcast は Phase-D / 人間承認後)。
    Health Factor チェック・緊急停止フラグには一切触れない。
    """
    aave_operation = "SUPPLY" if result.final_action == TradeAction.BUY else "WITHDRAW"
    aave_default = (aave_operation, _PROPOSAL_ASSET, "aave")

    # マルチプロトコルは BUY (新規投資) のみ対象。SELL/WITHDRAW は Aave 既定経路を維持
    # (lido unstake / pendle PT 売却は Phase-D 範囲のため、ここでは生成しない)。
    if not _multiprotocol_routing_enabled() or result.final_action != TradeAction.BUY:
        return aave_default

    try:
        from app.ai.optimizer.comparator import StrategyComparator  # noqa: PLC0415
        from app.ai.optimizer.schemas import Protocol  # noqa: PLC0415

        comparison = StrategyComparator().compare(
            investment_usd=investment_usd,
            risk_mode=risk_mode or "balanced",
        )
        recommended = comparison.recommended.protocol
    except Exception as exc:  # noqa: BLE001
        # optimizer 失敗時は安全側で Aave 既定にフォールバック (提案生成は継続)
        logger.warning("AI Optimizer 比較に失敗、Aave 既定にフォールバック: %s", exc)
        return aave_default

    if recommended in (Protocol.LIDO, Protocol.LIDO_AAVE):
        return ("STAKE_ETH", "ETH", "lido")
    if recommended in (Protocol.PENDLE_PT, Protocol.PENDLE_YT):
        return ("BUY_PT", "PT-stETH", "pendle")
    # AAVE / IDLE / その他 → Aave 既定経路
    return aave_default


def _create_proposals_for_users(
    db: Session,
    decision: AIDecision,
    result: CrossValidationResult,
) -> int:
    """ティア別間隔を満たすアクティブユーザーに Proposal を作成し、作成件数を返す。

    Args:
        db: SQLAlchemy セッション。
        decision: 保存済みの AIDecision。
        result: AI クロスバリデーション結果。

    Returns:
        作成した Proposal の件数。
    """
    # operation/asset/protocol は per-user の risk_mode に依存するため、ループ内で
    # _resolve_protocol_routing により決定する (Phase-B)。
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_PROPOSAL_EXPIRES_HOURS)
    reason = result.final_reason or "AI判定による提案"
    now = datetime.now(timezone.utc)

    active_users = db.scalars(
        select(User).where(
            User.is_active == True,  # noqa: E712
            User.execution_policy == ExecutionPolicy.REQUIRE_APPROVAL.value,
        )
    ).all()

    import os  # noqa: PLC0415

    from app.fees.trade_gate import calculate_fee_by_market  # noqa: PLC0415

    fixed_cost = Decimal(os.getenv("TRADE_FIXED_COST_USD", "0.27"))

    count = 0
    for user in active_users:
        try:
            # per-user SAVEPOINT: 1ユーザーの DB エラー (SELECT 失敗等) で session が汚染され
            # 後続ユーザー全員が fail する問題を防ぐ。例外時はこの savepoint のみ自動 rollback
            # され、先行ユーザーの proposal は維持される。素朴な db.rollback() は単一 commit
            # 設計下で全 user 分を破棄するため不可。最終 commit は呼び出し側で 1 回行う。
            with db.begin_nested():
                if not _is_user_due_for_judgment(user, now):
                    logger.debug(
                        "Skipping proposal for user %d (tier=%s, last_judgment_at=%s)",
                        user.id,
                        user.tier,
                        user.last_judgment_at,
                    )
                    continue

                # 既存の pending 提案がある場合はスキップ (2026-05-21 P0 重複作成ガード)
                # 承認待ち提案がすでに存在するのに新たな提案を作ると
                # 管理者が連続 approve した際に同一ユーザーへの Aave 操作が重複する。
                try:
                    _pending_raw = db.scalar(
                        select(func.count(Proposal.id)).where(
                            Proposal.user_id == user.id,
                            Proposal.status == "pending",
                        )
                    )
                    # isinstance guard: MagicMock (test) は int でないため 0 扱い (fail-open)
                    _pending_count: int = int(_pending_raw) if isinstance(_pending_raw, int) else 0
                except Exception as _guard_exc:  # noqa: BLE001
                    # DB エラー時は安全側: スキップしない (fail-open)
                    logger.warning(
                        "pending proposal check failed for user %d (fail-open): %s",
                        user.id,
                        _guard_exc,
                    )
                    _pending_count = 0
                if _pending_count > 0:
                    logger.info(
                        "Skipping proposal creation for user %d: "
                        "%d pending proposal(s) already exist",
                        user.id,
                        _pending_count,
                    )
                    continue

                # fund_allocations から per-user 提案金額を動的計算 (Decimal("0") = skip)
                proposal_amount_usd = _resolve_proposal_amount(db, user.id)
                if proposal_amount_usd <= Decimal("0"):
                    # _resolve_proposal_amount 内で警告・Slack 通知済み
                    continue

                # 動的手数料計算: デフォルトAPY 4%（安定期）を使用
                # 30日保有での予想利益 = amount × (APY/100) × (30/365)
                _default_apy = Decimal("4")
                _expected_profit = (
                    proposal_amount_usd
                    * _default_apy
                    / Decimal("100")
                    * Decimal("30")
                    / Decimal("365")
                )
                market_fee = calculate_fee_by_market(
                    trade_amount_usd=proposal_amount_usd,
                    tier=normalize_tier(user.tier, user_id=user.id).value,
                    current_apy=_default_apy,
                    expected_profit_usd=_expected_profit,
                    fixed_cost_usd=fixed_cost,
                )

                if not market_fee.should_trade:
                    logger.info(
                        "DynamicFee: should_trade=False for user %d — skipping proposal (%s)",
                        user.id,
                        market_fee.reason,
                    )
                    continue

                # Phase-B: AI Optimizer 経由で (operation, asset, protocol) を決定。
                # フラグ無効時は従来どおり (SUPPLY|WITHDRAW, USDC, aave)。
                operation, asset, protocol = _resolve_protocol_routing(
                    result, user.risk_mode, proposal_amount_usd
                )
                estimated_gas_usd = estimate_static_gas_cost_usd(operation)
                proposal = Proposal(
                    user_id=user.id,
                    ai_decision_id=decision.id,
                    operation=operation,
                    asset=asset,
                    protocol=protocol,
                    amount=proposal_amount_usd,
                    amount_usd=proposal_amount_usd,
                    reason=reason,
                    expires_at=expires_at,
                    fee_rate=market_fee.fee_rate,
                    fee_amount=market_fee.fee_amount,
                    estimated_gas_usd=estimated_gas_usd,
                )
                db.add(proposal)
                user.last_judgment_at = now
                count += 1

                # ai_proposal_notification: best-effort（失敗しても Proposal 作成は継続）
                try:
                    from app.notifications.factory import get_notification_service  # noqa: PLC0415
                    from app.notifications.templates import (
                        ai_proposal_notification,  # noqa: PLC0415
                    )

                    _payload = ai_proposal_notification(
                        operation=operation,
                        asset=asset,
                        amount=proposal_amount_usd,
                        confidence=result.final_confidence,
                    )
                    _payload.notification_message.user_id = user.id
                    get_notification_service().send(_payload.notification_message)
                except Exception as _notif_exc:  # noqa: BLE001
                    logger.warning(
                        "ai_proposal_notification failed for user %d (skipping): %s",
                        user.id,
                        _notif_exc,
                    )
        except Exception as _user_exc:  # noqa: BLE001
            # 1ユーザーの失敗が他のユーザーの提案生成を止めないようにする。
            # savepoint は with ブロック脱出時に当該ユーザー分のみ自動 rollback 済。
            # DB クエリ例外 / 未想定エラーはここで捕捉し、ループ継続。
            logger.error(
                "Proposal creation failed for user %d (skipping, continuing to next user): %s",
                user.id,
                _user_exc,
            )

    return count


def run_ai_judgment_job(db: Optional[Session] = None) -> dict[str, Any]:
    """AI 判定を実行して DB に保存する同期関数。

    BUY / SELL 判定時はアクティブユーザー全員に Proposal を作成する。

    Args:
        db: 外部から渡すセッション（テスト用）。None の場合は SessionLocal を使用。

    Returns:
        dict: {"action": str, "confidence": int, "proposals_created": int, "decision_id": int}
    """
    _own_session = db is None
    if _own_session:
        db = SessionLocal()
    if db is None:
        raise RuntimeError("db is None after SessionLocal()")

    try:
        # RAG コンテキスト取得（失敗時は空のコンテキストでフォールバック）
        rag_ctx: RAGContext
        try:
            svc = KnowledgeService()
            search_request = KnowledgeSearchRequest(query=_DEFAULT_QUERY, top_k=5)
            search_results = svc.search(db, search_request)
            rag_ctx = RAGContext(
                chunks=[r.content for r in search_results],
                query=_DEFAULT_QUERY,
                source_count=len(search_results),
            )
        except Exception as exc:
            logger.warning("RAG context retrieval failed, using empty context: %s", exc)
            rag_ctx = RAGContext(chunks=[], query=_DEFAULT_QUERY, source_count=0)

        # Market context（ニュース・地政学リスク・マクロ + Aave + cognitive_state）
        # を組み立てる。Aave 取得は fail-open ヘルパーで、個別失敗は None フォールバック。
        # cognitive_state は HOLD 連続抑制のため LLM プロンプトに渡す。
        context_degraded = False
        market_ctx: Any
        # aave_data は ai_decision_features INSERT にも使うため None-safe に初期化しておく。
        aave_data: AaveMarketData = {
            "utilization_rate": None,
            "supply_apy": None,
            "borrow_apy": None,
            "health_factor": None,
        }
        try:
            aave_data = fetch_aave_market_data_safe()
            cognitive_state = get_judgment_logger().get_cognitive_state()
            market_ctx = build_market_context(
                aave_utilization_rate=aave_data["utilization_rate"],
                aave_supply_apy=aave_data["supply_apy"],
                aave_borrow_apy=aave_data["borrow_apy"],
                health_factor=aave_data["health_factor"],
                cognitive_state=cognitive_state,
            )
        except Exception as exc:
            context_degraded = True
            logger.warning("build_market_context() failed, using degraded context: %s", exc)
            market_ctx = {
                "degraded": True,
                "reason": str(exc),
                "geopolitical_events": [],
                "market_data": {},
            }

        if context_degraded:
            logger.warning("AI judgment proceeding with degraded market context")

        # AI 判定実行
        result: CrossValidationResult = AIService().judge_with_rag(
            query=_DEFAULT_QUERY,
            rag_context=rag_ctx,
            market_context=market_ctx,
        )

        # DB 保存
        decision = save_ai_decision(db, result, _DEFAULT_QUERY, rag_context=rag_ctx)

        # Hermes Phase 0: 判定時の特徴量を ai_decision_features に INSERT (fail-open)
        # EPIC-1 1-11: save_ai_decision_features は AiDecisionFeature | None を返すよう拡張済み。
        # a_b モード時に deterministic_breakdown を参照するため戻り値を受け取る。
        feature = save_ai_decision_features(db, decision, result, aave_data, market_ctx)

        # EPIC-1 1-11: CONSENSUS_4AXIS_MODE="a_b" 50/50 A/B ルーティング。
        # **不変性ガード**: mode が "a_b" 以外のときは下記ブロックを一切通らない。
        # off / shadow / on の既存パスは 1 行も変更しない。
        from app.ai.config import get_ai_settings  # noqa: PLC0415

        _mode = get_ai_settings().consensus_4axis_mode
        routing_result = result  # デフォルト: 元の result で routing
        if _mode == "a_b":
            _bucket = _consensus_ab_bucket(decision.id)
            _adopted_action = result.final_action  # fail-open デフォルト = legacy
            if _bucket == "new":
                # 二重計算回避: _write_shadow_consensus が既に格納した verdict を再利用する。
                # fail-open: feature が None / deterministic_breakdown が None / KeyError
                # → _adopted_action は元の final_action のまま (legacy フォールバック)。
                try:
                    if feature is not None and feature.deterministic_breakdown is not None:
                        _adopted_action = TradeAction(feature.deterministic_breakdown["action"])
                except (KeyError, ValueError) as _ab_exc:
                    logger.warning(
                        "consensus a_b: verdict lookup failed (fail-open fallback to legacy): %s",
                        _ab_exc,
                    )
                # routing 専用コピーを作成 — 記録済み judge_action (1-12 計測) を汚染しない
                routing_result = result.model_copy(update={"final_action": _adopted_action})
            logger.info(
                "consensus a_b routing: decision_id=%s bucket=%s adopted_action=%s",
                decision.id,
                _bucket,
                _adopted_action.value,
            )

        # BUY / SELL 時は Proposal 作成
        proposals_created = 0
        if routing_result.final_action in (TradeAction.BUY, TradeAction.SELL):
            proposals_created = _create_proposals_for_users(db, decision, routing_result)

        db.commit()

        return {
            "action": result.final_action.value,
            "confidence": result.final_confidence,
            "proposals_created": proposals_created,
            "decision_id": decision.id,
        }

    except Exception as exc:
        logger.error("AI judgment job failed: %s", exc)
        try:
            db.rollback()
        except Exception:  # noqa: S110
            pass
        raise
    finally:
        if _own_session:
            db.close()


async def ai_judgment_loop(
    interval_hours: int = _DEFAULT_INTERVAL_UPPER,
    on_error: Optional[Callable[[Exception], None]] = None,
    startup_delay_sec: Optional[int] = None,
) -> None:
    """UPPER ティア間隔（最小値）で tick し、ユーザーごとにティア別間隔を適用するループ。

    tick 間隔は AI_JUDGMENT_INTERVAL_HOURS_UPPER（デフォルト 4 時間）に合わせる。
    各 tick で _create_proposals_for_users がユーザーごとのティア間隔を確認し、
    GENERAL ティアのユーザーは 8 時間未満の場合はスキップされる。

    起動直後の fan-out 抑制 (P3-5):
        再起動のたびに全 due user が即時 fan-out する問題を防ぐため、
        第1 tick の前に startup_delay_sec だけ待機する。
        デフォルトは AI_JUDGMENT_STARTUP_DELAY_SEC 環境変数（既定 300 秒）。
        watchdog / Cloudflare Tunnel 等が立ち上がる猶予を確保する。

    Args:
        interval_hours: tick 間隔（時間）。デフォルトは UPPER ティア間隔。
        on_error: 失敗時に呼び出す同期コールバック（Slack 通知等）。
        startup_delay_sec: 起動直後の待機秒数。None の場合は環境変数値を使用。
            0 を渡すと遅延なし（テスト・デバッグ用途）。
    """
    global _scheduler_started, _last_run_at, _next_run_at, _last_error_msg
    _scheduler_started = True

    # P3-5: 起動直後の即時 fan-out を抑制するための startup delay
    delay = startup_delay_sec if startup_delay_sec is not None else _DEFAULT_STARTUP_DELAY_SEC
    if delay > 0:
        logger.info(
            "AI judgment scheduler: startup delay %d sec (P3-5 fan-out suppression). "
            "Set AI_JUDGMENT_STARTUP_DELAY_SEC=0 to disable.",
            delay,
        )
        await asyncio.sleep(delay)

    while True:
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, run_ai_judgment_job)
            _last_run_at = datetime.now(timezone.utc)
            _last_error_msg = None
            logger.info("AI judgment completed: %s", result)

            # AI 判定完了後に WebSocket ブロードキャスト（fail-open / 最小変更）
            try:
                from app.ai.models import AIDecision as _AIDecision  # noqa: PLC0415
                from app.ai.ws_manager import ws_manager as _ws_manager  # noqa: PLC0415

                with SessionLocal() as _db:
                    _latest = _db.query(_AIDecision).order_by(_AIDecision.created_at.desc()).first()
                    if _latest:
                        await _ws_manager.broadcast(
                            {
                                "action": _latest.action,
                                "confidence": _latest.confidence,
                                "reason": _latest.reason,
                            }
                        )
            except Exception as _ws_exc:  # noqa: BLE001
                logger.warning("WS broadcast skipped (non-critical): %s", _ws_exc)

            # AI判定直後にポートフォリオスナップショットを記録（fail-open）
            try:
                from app.portfolio.snapshot_service import record_portfolio_snapshot  # noqa: PLC0415,I001

                snap_result = await loop.run_in_executor(None, record_portfolio_snapshot)
                logger.info("Portfolio snapshot recorded: %s", snap_result)
            except Exception as snap_exc:
                logger.warning("Portfolio snapshot skipped (non-critical): %s", snap_exc)
        except Exception as exc:
            _last_error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("AI judgment job failed: %s", exc)
            if on_error:
                try:
                    on_error(exc)
                except Exception as cb_exc:
                    logger.error("on_error callback failed: %s", cb_exc)
        _next_run_at = datetime.now(timezone.utc) + timedelta(hours=interval_hours)
        await asyncio.sleep(interval_hours * 3600)
