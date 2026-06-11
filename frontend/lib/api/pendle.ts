// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { getJson } from "./http";

// ── Types ─────────────────────────────────────────────────────────────────

/**
 * Pendle PT/YT ポジション情報
 * バックエンド API が未実装のため、fetchPendlePositions は
 * エラー時に null を返すフォールバック実装となっています。
 */
export interface PendlePosition {
  /** ポジションID */
  id: string;
  /** 対象マーケットアドレス */
  market_address: string;
  /** 原資産シンボル (例: "stETH", "USDC") */
  underlying_asset: string;
  /** PT (元本トークン) 保有量 — バックエンドから文字列で返却 */
  pt_amount: string;
  /** YT (利回りトークン) 保有量 — バックエンドから文字列で返却 */
  yt_amount: string;
  /** PT 現在価格 USD — バックエンドから文字列で返却 */
  pt_price_usd: string;
  /** YT 現在価格 USD — バックエンドから文字列で返却 */
  yt_price_usd: string;
  /** 推定 APY — バックエンドから文字列で返却 */
  implied_apy: string;
  /** 満期日 ISO8601 形式 */
  maturity: string;
  /** 満期まで残り日数 */
  days_to_maturity: number;
  /** ポジション取得時刻 ISO8601 */
  fetched_at: string;
}

export interface PendlePositionResponse {
  positions: PendlePosition[];
  total_value_usd: string;
}

// ── APY 履歴チャート用型 ──────────────────────────────────────────────────

export interface PendleApyPoint {
  /** UTC 日付 YYYY-MM-DD */
  date: string;
  /** APY 値 — バックエンドから文字列で返却 */
  apy: string;
  /** 基準資産シンボル */
  underlying_asset: string;
}

// ── API 関数 ──────────────────────────────────────────────────────────────

/**
 * Pendle ポジション一覧を取得します。
 * バックエンド API が未実装 (404/500) の場合は null を返します。
 */
export async function fetchPendlePositions(): Promise<PendlePositionResponse | null> {
  try {
    return await getJson<PendlePositionResponse>("/api/protocols/pendle/positions");
  } catch {
    // バックエンド未実装のためフォールバック
    return null;
  }
}

/**
 * Pendle APY 履歴を取得します。
 * バックエンド API が未実装 (404/500) の場合は空配列を返します。
 */
export async function fetchPendleApyHistory(
  marketAddress: string,
  days = 30
): Promise<PendleApyPoint[]> {
  try {
    return await getJson<PendleApyPoint[]>(
      `/api/protocols/pendle/markets/${encodeURIComponent(marketAddress)}/apy-history?days=${days}`
    );
  } catch {
    // バックエンド未実装のためフォールバック
    return [];
  }
}
