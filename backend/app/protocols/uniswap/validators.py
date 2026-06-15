# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Uniswap V4 スワップ純粋バリデータ（Phase 1 scaffold）。

本モジュールは **純粋関数のみ** を提供する。
I/O・web3・HTTP・秘密鍵へのアクセスは一切行わない。
外部副作用のないコードのみで構成する（テスト容易性・安全境界の明確化）。

実行系コード（SDK calldata 取得 / tx 署名 / broadcast）は
HUMAN-REVIEW-REQUIRED スコープ（Phase 2/3）で別ファイルに追加する。
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.aave.slippage_guard import SlippageGuard
from app.protocols.uniswap.schemas import UniswapV4SwapEstimate, UniswapV4SwapIntent

logger = logging.getLogger(__name__)

# 単一取引上限: ポートフォリオの 10%（Security Rules §3）
_MAX_SINGLE_TRADE_RATIO = Decimal("0.10")

# SlippageGuard は is_stablecoin 判定の再利用のみ。本体は改変しない。
_slippage_guard = SlippageGuard()


def validate_swap_intent(
    intent: UniswapV4SwapIntent,
    now_unix: int,
) -> UniswapV4SwapEstimate:
    """Uniswap V4 スワップ意図をバリデートし推定結果を返す。

    純粋関数: 引数のみから結果を計算する。I/O・外部状態参照なし。

    Args:
        intent: バリデート対象のスワップ意図
        now_unix: 現在時刻（Unix 秒）。テスト時は任意の値を注入可能

    Returns:
        UniswapV4SwapEstimate: バリデーション結果。
          - is_valid=True: 全チェック通過
          - is_valid=False: validation_errors にエラー詳細を格納

    Security:
        - deadline_unix <= now_unix: 期限切れとして拒否（fail-closed）
        - token_in == token_out: 無意味なスワップとして拒否
        - receiver が空文字: 宛先不明として拒否
        - amount_in_usd と portfolio_value_usd の一方のみ指定: 10%上限検証不能→拒否
        - amount_in_usd > portfolio_value_usd * 0.10: 単一取引10%上限違反として拒否
        - slippage の範囲: スキーマ側で担保済み（gt=0, le=0.05）
        - amount_in > 0: スキーマ側で担保済み（gt=0）
    """
    errors: list[str] = []

    # 1. deadline チェック（期限切れは即座に拒否）
    if intent.deadline_unix <= now_unix:
        errors.append(
            f"deadline_unix ({intent.deadline_unix}) が現在時刻 ({now_unix}) 以前: スワップ期限切れ"
        )

    # 2. 同一トークンチェック
    if intent.token_in.lower() == intent.token_out.lower():
        errors.append(f"token_in と token_out が同一: {intent.token_in} — 無意味なスワップは拒否")

    # 3. receiver 非空チェック
    if not intent.receiver.strip():
        errors.append("receiver が空文字: 受取アドレスを指定してください")

    # 4. 単一取引10%上限チェック（Security Rules §3）
    #    amount_in_usd または portfolio_value_usd のどちらか一方のみ指定は fail-closed で拒否。
    #    両方 None の場合は上限チェックをスキップ（USD 評価不能）。
    #    両方 None でない場合のみ比較する。
    has_amount_usd = intent.amount_in_usd is not None
    has_portfolio_usd = intent.portfolio_value_usd is not None

    if has_amount_usd != has_portfolio_usd:
        # 片方のみ指定: 10%上限が正確に検証できないため fail-closed で拒否
        errors.append(
            "amount_in_usd と portfolio_value_usd はどちらも指定するか、どちらも省略してください。"
            "片方のみの指定では単一取引10%上限を検証できないため拒否します（fail-closed）"
        )
    elif intent.amount_in_usd is not None and intent.portfolio_value_usd is not None:
        # 型ガード: is not None チェックにより mypy が Decimal として推論する
        amount_usd: Decimal = intent.amount_in_usd
        portfolio_usd: Decimal = intent.portfolio_value_usd

        if portfolio_usd > Decimal("0") and amount_usd > portfolio_usd * _MAX_SINGLE_TRADE_RATIO:
            errors.append(
                f"単一取引上限超過: amount_in_usd={amount_usd} が "
                f"portfolio_value_usd={portfolio_usd} の {_MAX_SINGLE_TRADE_RATIO * 100}% を超えています"
            )

    # 5. ステーブルコイン判定（SlippageGuard 再利用、本体非改変）
    #    ステーブルコイン同士のスワップはスリッページ許容幅が十分か補足情報として記録
    #    （Phase 1 では reject は行わない。Phase 2 で quoting API 連携後に判断）
    token_in_symbol = _extract_symbol(intent.token_in)
    token_out_symbol = _extract_symbol(intent.token_out)
    is_stablecoin_in = _slippage_guard.is_stablecoin(token_in_symbol)
    is_stablecoin_out = _slippage_guard.is_stablecoin(token_out_symbol)

    if is_stablecoin_in and is_stablecoin_out:
        logger.debug(
            "UniswapV4 validate_swap_intent: ステーブルコイン同士のスワップ (%s -> %s)。"
            "slippage=%.4f",
            token_in_symbol,
            token_out_symbol,
            intent.slippage,
        )

    is_valid = len(errors) == 0

    logger.debug(
        "validate_swap_intent: is_valid=%s errors=%d chain=%s token_in=%s token_out=%s",
        is_valid,
        len(errors),
        intent.chain,
        intent.token_in[:10] + "...",
        intent.token_out[:10] + "...",
    )

    return UniswapV4SwapEstimate(
        amount_out_estimate=None,  # Phase 2 (quoting API) で設定
        min_amount_out=None,  # Phase 2 で compute_min_amount_out を適用
        price_impact_pct=None,  # Phase 2 (quoting API) で設定
        is_valid=is_valid,
        validation_errors=errors,
    )


def compute_min_amount_out(
    amount_out_estimate: Decimal,
    slippage: Decimal,
) -> Decimal:
    """最小受取量を計算する（純粋関数）。

    Phase 2 以降で quoting API から amount_out_estimate を取得した後に呼び出す。

    Args:
        amount_out_estimate: 推定受取量（Decimal）
        slippage: スリッページ許容幅（例: Decimal("0.005") = 0.5%）

    Returns:
        最小受取量: amount_out_estimate * (1 - slippage)

    Note:
        全計算を Decimal で行う（float 禁止）。
        slippage の範囲検証はスキーマ（UniswapV4SwapIntent）側で担保済み。
    """
    return amount_out_estimate * (Decimal("1") - slippage)


def _extract_symbol(token_address_or_symbol: str) -> str:
    """アドレスまたはシンボルからシンボル相当文字列を返す。

    SlippageGuard.is_stablecoin はシンボル（"USDC" 等）を期待する。
    アドレス形式（"0x..."）の場合は大文字変換のみ行い、
    一致しなければ is_stablecoin は False を返す（fail-open）。
    シンボル文字列の場合は大文字変換して返す。

    純粋関数: 外部参照なし。
    """
    stripped = token_address_or_symbol.strip()
    if stripped.startswith("0x") or stripped.startswith("0X"):
        # アドレス形式: そのまま渡す（_STABLECOIN_SYMBOLS に一致しないため False 返却）
        return stripped.upper()
    return stripped.upper()
