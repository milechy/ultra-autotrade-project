// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/aave.ts
/**
 * Aave 関連 API クライアント
 * - getStressTest(): GET /api/aave/stress-test
 * - getPoolHealth(): GET /api/aave/pool-health
 * - getRewards(): GET /api/aave/rewards
 * - claimRewards(): POST /api/aave/rewards/claim
 * - getEMode(): GET /api/aave/emode
 * - setEMode(): POST /api/aave/emode
 */

import { getJson, postJson } from "./http";

// ---------------------------------------------------------------------------
// ストレステスト
// ---------------------------------------------------------------------------

export interface StressTestScenario {
  price_drop_pct: string; // Decimal 文字列 (例: "0.10")
  simulated_hf: string | null; // シミュレーション後 HF（Decimal 文字列）
  collateral_after_usd: string | null; // 担保 USD 評価額（Decimal 文字列）
}

export interface StressTestResult {
  wallet_address: string;
  current_hf: string | null; // Decimal 文字列
  current_collateral_usd: string | null; // Decimal 文字列
  current_debt_usd: string | null; // Decimal 文字列
  liquidation_threshold: string | null; // Decimal 文字列 (例: "0.80")
  scenarios: StressTestScenario[];
  error: string | null;
}

export async function getStressTest(): Promise<StressTestResult> {
  return getJson<StressTestResult>("/api/aave/stress-test");
}

// ---------------------------------------------------------------------------
// プール赤字ヘルス
// ---------------------------------------------------------------------------

export interface PoolDeficitInfo {
  asset_symbol: string; // 例: "USDC", "WETH"
  deficit_usd: string; // Decimal 文字列
  alert_triggered: boolean;
}

export interface PoolHealthResult {
  chain_name: string;
  deficits: PoolDeficitInfo[];
  total_deficit_usd: string; // Decimal 文字列
  alert_triggered: boolean;
  error: string | null;
}

export async function getPoolHealth(): Promise<PoolHealthResult> {
  return getJson<PoolHealthResult>("/api/aave/pool-health");
}

// ---------------------------------------------------------------------------
// リワード
// ---------------------------------------------------------------------------

export interface ClaimableReward {
  asset_name: string;
  reward_token_address: string;
  amount: string;
  amount_usd: string;
}

export interface RewardsResponse {
  rewards: ClaimableReward[];
  total_usd: string;
  fetched_at: string;
  note?: string;
}

export interface ClaimRewardsResponse {
  claimed: boolean;
  total_usd: string;
  rewards: ClaimableReward[];
  supply_tx_hash: string | null;
  skip_reason: string | null;
  error: string | null;
  claimed_at: string | null;
}

/**
 * GET /aave/rewards — 未請求リワードを取得する（viewer 以上）
 */
export async function getRewards(): Promise<RewardsResponse> {
  return getJson<RewardsResponse>("/api/aave/rewards");
}

/**
 * POST /aave/rewards/claim — リワードを手動 Claim する（admin のみ）
 */
export async function claimRewards(): Promise<ClaimRewardsResponse> {
  return postJson<ClaimRewardsResponse>("/api/aave/rewards/claim", {});
}

// ---------------------------------------------------------------------------
// eMode
// ---------------------------------------------------------------------------

export interface EModeInfo {
  category_id: number;
  label: string;
  ltv_bps: string; // Decimal 文字列
  liquidation_threshold_bps: string; // Decimal 文字列
}

export interface EModeRecommendation {
  current_category_id: number;
  recommended_category_id: number;
  current_ltv_bps: string; // Decimal 文字列
  recommended_ltv_bps: string; // Decimal 文字列
  ltv_improvement_pct: string; // Decimal 文字列
  reason: string;
  collateral_assets: string[];
}

export interface EModeGetResponse {
  current_emode: EModeInfo;
  recommendation: EModeRecommendation;
  fetched_at: string;
}

export interface EModeSetRequest {
  category_id: number;
  dry_run?: boolean;
}

export interface EModeSetResponse {
  category_id: number;
  tx_hash: string | null;
  dry_run: boolean;
  message: string;
}

/**
 * GET /aave/emode — 現在の eMode 設定と最適化推奨を取得する（viewer 以上）
 */
export async function getEMode(): Promise<EModeGetResponse> {
  return getJson<EModeGetResponse>("/api/aave/emode");
}

/**
 * POST /aave/emode — eMode カテゴリを切り替える（admin のみ）
 */
export async function setEMode(req: EModeSetRequest): Promise<EModeSetResponse> {
  return postJson<EModeSetResponse>("/api/aave/emode", req);
}
