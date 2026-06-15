# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
統合ポートフォリオ集約関数

3ソース (Aave V3 / Privy Wallet / Bybit CEX) の SourceBalance を受け取り、
UnifiedPortfolioView を返す純粋関数モジュール。

設計書: docs/59_unified_portfolio_dashboard_design.md

【厳守】
- 実 API / web3 / ccxt / aave / requests / httpx を一切 import しない
- 全金融計算は Decimal 型 (float 禁止 / CLAUDE.md Security Rule 11)
- fail-open: available=False または欠落ソースも grand_total から除外するが
  他ソースの表示は継続する
- ゼロ除算ガード: grand_total=0 の場合 allocation_pct は全て 0
"""

from decimal import Decimal

from app.portfolio.aggregation_schemas import (
    SourceAllocation,
    SourceBalance,
    UnifiedPortfolioInput,
    UnifiedPortfolioView,
)

# ソース定義順序 (表示順固定)
_SOURCE_ORDER = ("aave", "wallet", "cex")


def _get_source_usd(source: SourceBalance | None) -> Decimal:
    """ソースが存在しかつ available=True の場合のみ total_usd を返す。

    欠落 (None) または available=False の場合は Decimal("0") を返す。
    これにより fail-open かつ grand_total への誤算入を防ぐ。
    """
    if source is None:
        return Decimal("0")
    if not source.available:
        return Decimal("0")
    return source.total_usd


def _calc_allocation_pct(source_usd: Decimal, grand_total: Decimal) -> Decimal:
    """配分比率 (%) を計算する。grand_total=0 の場合は 0 を返す (ゼロ除算ガード)。

    Args:
        source_usd: ソースの USD 残高
        grand_total: 全ソース合算 USD

    Returns:
        配分比率 (0-100)。grand_total=0 の場合は Decimal("0")。
    """
    if grand_total == Decimal("0"):
        return Decimal("0")
    return (source_usd / grand_total * Decimal("100")).quantize(Decimal("0.01"))


def aggregate_portfolio(input: UnifiedPortfolioInput) -> UnifiedPortfolioView:  # noqa: A002
    """3ソースの残高を集約して UnifiedPortfolioView を生成する。

    fail-open 設計:
    - 各ソースが None (取得失敗) または available=False の場合、
      そのソースの USD は grand_total から除外される
    - 他ソースが正常な場合は degraded=True で表示を継続する

    二重計上なし:
    - wallet.total_usd は Aave supply 分を含まない
      (wallet_balance_service.py L13 に明記)
    - aave_net_usd は total_collateral_usd - total_debt_usd (純資産)
      入力側で計算済みの total_usd を使用

    Args:
        input: 3ソースの SourceBalance (各 Optional)

    Returns:
        UnifiedPortfolioView: 集約済みポートフォリオビュー
    """
    # --- 各ソースの有効 USD を取得 (fail-open) ---
    aave_usd = _get_source_usd(input.aave)
    wallet_usd = _get_source_usd(input.wallet)
    cex_usd = _get_source_usd(input.cex)

    # --- grand_total 合算 (available ソースのみ) ---
    grand_total = aave_usd + wallet_usd + cex_usd

    # --- ソース別配分計算 ---
    def _make_allocation(key: str, source: SourceBalance | None, usd: Decimal) -> SourceAllocation:
        available = source.available if source is not None else False
        return SourceAllocation(
            source=key,
            total_usd=usd,
            allocation_pct=_calc_allocation_pct(usd, grand_total),
            available=available,
        )

    allocations = [
        _make_allocation("aave", input.aave, aave_usd),
        _make_allocation("wallet", input.wallet, wallet_usd),
        _make_allocation("cex", input.cex, cex_usd),
    ]

    # --- sources_available カウント ---
    # available=True かつ欠落でないソースを数える
    sources_available = sum(
        1 for src in (input.aave, input.wallet, input.cex) if src is not None and src.available
    )

    # --- degraded フラグ ---
    # 1ソース以上が欠落 (None) または available=False の場合 True
    degraded = sources_available < 3  # sources_total=3 固定

    # --- Health Factor: Aave ソースが available な場合のみ透過 ---
    health_factor: Decimal | None = None
    if input.aave is not None and input.aave.available and input.aave.health_factor is not None:
        health_factor = input.aave.health_factor

    return UnifiedPortfolioView(
        grand_total_usd=grand_total,
        aave_net_usd=aave_usd,
        wallet_usd=wallet_usd,
        cex_usd=cex_usd,
        health_factor=health_factor,
        allocations=allocations,
        sources_available=sources_available,
        sources_total=3,
        degraded=degraded,
    )
