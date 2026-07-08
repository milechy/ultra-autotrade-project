"""提案チェーン ゲートトレーサ (read-only diagnostic)。

「実ユーザーに提案が 1 件届く」までに直列に並ぶ関門を 1 つずつ検査し、
いま**どの関門で止まっているか**を名指しで報告する。副作用なし (SELECT のみ)。

背景 (2026-07-08):
    AI 判定 → 提案生成 → 表示 → 執行 のチェーンは ~15 個の独立した関門の AND で
    成立する。どれか 1 個ズレると症状は毎回同じ「提案が出ない」になり、犯人を 1 人ずつ
    実機で特定するしかなかった (1 ヶ月モグラ叩き)。本ツールは全関門の現在値を一度に
    可視化し、「毎日謎バグ」を「関門 X が赤 → X を直す」に変える。

設計:
    - 実ロジックの private ヘルパー/定数を ai_judgment_scheduler から import して、
      判定間隔・入金ゲート・重複ガード等の写像がコード本体とドリフトしないようにする。
    - 「決定層」(AI が BUY/SELL に到達するか) と「配信層」(BUY が出たとして各ユーザーに
      提案が届くか) を**独立に**評価する。決定層が HOLD でも配信層の準備状況を同時に
      見せることで、残る関門を一度に全部surfaceする (1 個ずつではなく)。

実行:
    docker exec <backend-container> python -m app.diagnostics.proposal_chain
    docker exec <backend-container> python -m app.diagnostics.proposal_chain --json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AIDecision, AiDecisionFeature
from app.auth.models import User
from app.automation.ai_judgment_scheduler import (
    _get_tier_interval_hours,
    _is_user_due_for_judgment,
)
from app.partner.allocation_models import FundAllocation
from app.proposals.models import Proposal
from app.users.deposit_policy import MIN_DEPOSIT_USD

# 提案は BUY/SELL のみで生成される (HOLD は全弾き)。indicator/macro の合格閾値。
_CONF_THRESHOLD = 70


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _flag(name: str, default: str = "0") -> bool:
    return _env(name, default).lower() in ("1", "true", "yes")


def _extract_agent(agent_signals: Any, agent_name: str) -> dict[str, Any]:
    """agent_signals JSON から指定エージェント (indicator/macro 等) の bias/confidence を抽出。

    agent_signals の形が dict / list どちらでも拾えるよう防御的に実装する。
    見つからなければ {} を返す (fail-open)。
    """
    if not agent_signals:
        return {}
    try:
        # dict 形式: {"indicator": {"bias": ..., "confidence": ...}, ...}
        if isinstance(agent_signals, dict):
            node = agent_signals.get(agent_name)
            if isinstance(node, dict):
                return node
            # {"agents": [...]} のような入れ子も一応見る
            inner = agent_signals.get("agents")
            if isinstance(inner, list):
                return _extract_agent(inner, agent_name)
            return {}
        # list 形式: [{"name"/"agent": "indicator", "bias": ..., "confidence": ...}, ...]
        if isinstance(agent_signals, list):
            for item in agent_signals:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("agent") or "").lower()
                if name == agent_name.lower():
                    return item
    except Exception:  # noqa: BLE001  診断ツールは絶対に落とさない
        return {}
    return {}


def _bias_conf(node: dict[str, Any]) -> tuple[Optional[str], Optional[int]]:
    bias = node.get("bias")
    conf = node.get("confidence")
    try:
        conf_int = int(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_int = None
    return (str(bias) if bias is not None else None, conf_int)


def diagnose(db: Session) -> dict[str, Any]:
    """提案チェーンの全関門を検査し、構造化レポートを返す (read-only)。"""
    now = datetime.now(timezone.utc)
    app_env = _env("APP_ENV", "unknown")

    # ── 環境レベルの関門 ──
    disable_bg = _flag("DISABLE_BACKGROUND_MONITORING")
    disable_sched = _flag("DISABLE_AI_JUDGMENT_SCHEDULER")
    macro_relax = _flag("AI_STAGING_RELAX_MACRO_GATE") and app_env.lower() != "production"
    multiprotocol = _flag("AI_OPTIMIZER_MULTIPROTOCOL_ENABLED")

    env_gates = {
        "app_env": app_env,
        "ai_judgment_scheduler_enabled": not disable_sched,
        "background_monitoring_enabled": not disable_bg,
        # proposal_timeout(期限切れ→expire) は 2026-07-08 以降 background flag と独立で常時ON。
        # 旧バージョンでは disable_bg=True が期限切れ housekeeping まで止めていた点に注意。
        "expiry_housekeeping_note": (
            "proposal_timeout is always-on (post 2026-07-08 fix); "
            "if this build predates that fix, DISABLE_BACKGROUND_MONITORING=1 also stops expiry"
        ),
        "macro_gate_relaxed_non_prod": macro_relax,
        "multiprotocol_routing_enabled": multiprotocol,
        "min_deposit_usd": str(MIN_DEPOSIT_USD),
    }

    # ── 最新 AI 判定 (決定層) ──
    latest: Optional[AIDecision] = db.scalars(
        select(AIDecision).order_by(AIDecision.created_at.desc()).limit(1)
    ).first()

    decision_layer: dict[str, Any] = {"has_decision": latest is not None}
    if latest is not None:
        created = latest.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_h = (now - created).total_seconds() / 3600.0
        feature = db.scalars(
            select(AiDecisionFeature).where(AiDecisionFeature.ai_decision_id == latest.id)
        ).first()
        ind_bias, ind_conf = _bias_conf(
            _extract_agent(getattr(feature, "agent_signals", None), "indicator")
        )
        mac_bias, mac_conf = _bias_conf(
            _extract_agent(getattr(feature, "agent_signals", None), "macro")
        )
        # tick は UPPER 間隔 (既定 4h)。2 周期以上判定が無ければスケジューラ停滞の疑い。
        tick_h = _get_tier_interval_hours("UPPER")
        decision_layer.update(
            {
                "decision_id": latest.id,
                "action": latest.action,
                "final_confidence": latest.confidence,
                "age_hours": round(age_h, 2),
                "scheduler_alive": age_h <= max(8.0, tick_h * 2),
                "indicator": {"bias": ind_bias, "confidence": ind_conf},
                "macro": {"bias": mac_bias, "confidence": mac_conf},
                "raw_agent_signals": getattr(feature, "agent_signals", None),
            }
        )
        # 決定層ゲート判定
        decision_layer["gate_directional"] = latest.action in ("BUY", "SELL")
        decision_layer["gate_indicator_conf>=70"] = (ind_conf or 0) >= _CONF_THRESHOLD
        decision_layer["gate_macro_conf>=70"] = macro_relax or (mac_conf or 0) >= _CONF_THRESHOLD

    # ── 配信層 (per-user, 決定層とは独立に評価) ──
    # 「もし BUY が出たら」このユーザーに提案が届くかを、各関門ごとに検査する。
    users = db.scalars(select(User).where(User.is_active == True)).all()  # noqa: E712
    user_reports: list[dict[str, Any]] = []
    for u in users:
        alloc_raw = (
            db.query(func.sum(FundAllocation.allocated_amount_usd))
            .filter(
                FundAllocation.tester_user_id == u.id,
                FundAllocation.status == "active",
            )
            .scalar()
        )
        allocated = Decimal(str(alloc_raw)) if alloc_raw else Decimal("0")
        wallet = (u.smart_wallet_address or u.wallet_address) or None

        # funded 判定 (allocation 経路のみ確定評価。wallet 残高経路は RPC が要るため未評価)
        if allocated >= MIN_DEPOSIT_USD:
            funded, funded_via = True, "allocation"
        elif allocated > 0:
            funded, funded_via = False, f"allocation<${MIN_DEPOSIT_USD}"
        elif wallet:
            funded, funded_via = None, "wallet(needs RPC — not evaluated)"
        else:
            funded, funded_via = False, "unfunded"

        # pending の内訳: fresh(期限内=ブロック要因) と stale(期限切れ残留=修正前の永久ブロック元凶)
        pendings = db.scalars(
            select(Proposal).where(Proposal.user_id == u.id, Proposal.status == "pending")
        ).all()

        def _is_past(p: Proposal) -> bool:
            exp = p.expires_at
            if exp is None:
                return False
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return exp < now

        stale = [p for p in pendings if _is_past(p)]
        fresh = [p for p in pendings if not _is_past(p)]
        due = _is_user_due_for_judgment(u, now)

        # このユーザーが BUY 時に提案を受け取れるか (配信層の合否)
        blockers: list[str] = []
        if u.execution_policy != "require_approval":
            blockers.append(f"policy={u.execution_policy}(not require_approval)")
        if funded is False:
            blockers.append(f"not_funded({funded_via})")
        if funded is None:
            blockers.append("funded_unknown(wallet path needs RPC)")
        if not due:
            blockers.append(f"within_tier_interval(tier={u.tier})")
        if fresh:
            blockers.append(f"blocking_pending x{len(fresh)}")

        user_reports.append(
            {
                "user_id": u.id,
                "role": u.role,
                "tier": u.tier,
                "execution_policy": u.execution_policy,
                "funded": funded,
                "funded_via": funded_via,
                "allocated_usd": str(allocated),
                "wallet_set": bool(wallet),
                "due_for_judgment": due,
                "pending_total": len(pendings),
                "pending_fresh": len(fresh),
                "pending_stale": len(stale),
                "stale_pending_ids": [p.id for p in stale],
                "would_receive_on_buy": len(blockers) == 0,
                "blockers": blockers,
            }
        )

    deliverable = [r for r in user_reports if r["would_receive_on_buy"]]

    # ── 総合判定 ──
    if latest is None:
        verdict = "NO_DECISION: ai_decisions が空。スケジューラ未稼働か初回起動前。"
    elif not decision_layer.get("scheduler_alive", True):
        verdict = (
            f"SCHEDULER_STALLED: 最新判定が {decision_layer['age_hours']}h 前。"
            "スケジューラ停滞の疑い。"
        )
    elif not deliverable:
        verdict = (
            "DELIVERY_BLOCKED: BUY が出ても提案を受け取れる有効ユーザーが 0。"
            " 各ユーザーの blockers を参照 (funded/pending/interval/policy)。"
        )
    elif latest.action not in ("BUY", "SELL"):
        ic = decision_layer["indicator"]["confidence"]
        mc = decision_layer["macro"]["confidence"]
        verdict = (
            f"DECISION_HOLD: 配信層は OK ({len(deliverable)} 名が受信可) だが最新判定が "
            f"{latest.action} (indicator conf={ic} / macro conf={mc})。"
            " 決定層のゲート未達で提案未生成。"
        )
    else:
        verdict = (
            f"REACHABLE: 最新判定 {latest.action} かつ {len(deliverable)} 名が受信可。"
            " チェーンは疎通。"
        )

    return {
        "generated_at": now.isoformat(),
        "verdict": verdict,
        "env_gates": env_gates,
        "decision_layer": decision_layer,
        "delivery_layer": {
            "active_users": len(user_reports),
            "deliverable_on_buy": len(deliverable),
            "users": user_reports,
        },
    }


def _print_human(report: dict[str, Any]) -> None:
    d = report["decision_layer"]
    e = report["env_gates"]
    print("=" * 72)
    print(f"提案チェーン診断  env={e['app_env']}  @ {report['generated_at']}")
    print("=" * 72)
    print(f"\n▶ 総合判定: {report['verdict']}\n")

    print("── 環境ゲート ──")
    print(f"  AI判定スケジューラ有効 : {e['ai_judgment_scheduler_enabled']}")
    print(f"  背景監視ループ有効     : {e['background_monitoring_enabled']}")
    print(f"  macroゲート緩和(非本番): {e['macro_gate_relaxed_non_prod']}")
    print(f"  マルチプロトコル       : {e['multiprotocol_routing_enabled']}")
    print(f"  最低入金額(USD)        : {e['min_deposit_usd']}")

    print("\n── 決定層 (AIがBUY/SELLに到達するか) ──")
    if not d.get("has_decision"):
        print("  判定なし (ai_decisions 空)")
    else:
        print(f"  最新判定    : {d['action']} conf={d['final_confidence']} ({d['age_hours']}h前)")
        print(f"  scheduler   : {'alive' if d['scheduler_alive'] else 'STALLED'}")
        print(
            f"  indicator   : bias={d['indicator']['bias']} conf={d['indicator']['confidence']}"
            f"  [gate>=70: {d.get('gate_indicator_conf>=70')}]"
        )
        print(
            f"  macro       : bias={d['macro']['bias']} conf={d['macro']['confidence']}"
            f"  [gate>=70: {d.get('gate_macro_conf>=70')}]"
        )
        print(f"  directional : {d.get('gate_directional')} (BUY/SELLのみ提案生成)")

    dl = report["delivery_layer"]
    print(
        f"\n── 配信層 (BUYが出たら誰に届くか) : {dl['deliverable_on_buy']}/{dl['active_users']} 名 受信可 ──"
    )
    for u in dl["users"]:
        mark = "✅" if u["would_receive_on_buy"] else "🚫"
        reason = "" if u["would_receive_on_buy"] else "  ← " + "; ".join(u["blockers"])
        stale = f"  [stale_pending={u['stale_pending_ids']}]" if u["pending_stale"] else ""
        print(
            f"  {mark} user {u['user_id']:>3} ({u['role']}/{u['tier']}/{u['execution_policy']}) "
            f"funded={u['funded']}({u['funded_via']}) pending={u['pending_fresh']}f/"
            f"{u['pending_stale']}s{reason}{stale}"
        )
    print()


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    from app.database import SessionLocal  # noqa: PLC0415  遅延 import (import 時の副作用回避)

    db = SessionLocal()
    try:
        report = diagnose(db)
    finally:
        db.close()

    if "--json" in argv:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
