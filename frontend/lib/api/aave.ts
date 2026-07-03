// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/aave.ts
/**
 * Aave 関連 API クライアント
 * - getPoolHealth(): GET /api/aave/pool-health
 * - claimRewards(): POST /api/aave/rewards/claim
 * - getBorrowRates(): GET /api/aave/borrow-rates
 * - getEMode(): GET /api/aave/emode
 * - setEMode(): POST /api/aave/emode
 *
 * NOTE: getStressTest()/getRewards() は呼出元ゼロのため削除（2026-06-22 監査 fe-10）。
 * 各 read は画面側 useAuthFetch がインラインで担当。型は保持。
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
 * POST /aave/rewards/claim — リワードを手動 Claim する（admin のみ）
 */
export async function claimRewards(): Promise<ClaimRewardsResponse> {
  return postJson<ClaimRewardsResponse>("/api/aave/rewards/claim", {});
}

// ---------------------------------------------------------------------------
// GHO 借入金利比較
// ---------------------------------------------------------------------------

export interface BorrowRateComparison {
  /** USDC 変動借入 APR（年率、Decimal 文字列） */
  usdc_apr: string;
  /** GHO 変動借入 APR（割引前、年率、Decimal 文字列） */
  gho_variable_apr: string;
  /** GHO 実効借入 APR（stkAAVE 割引後、年率、Decimal 文字列） */
  gho_effective_apr: string;
  /** 推奨借入通貨: "GHO" | "USDC" */
  recommendation: string;
  /** GHO 推奨時の年間節約額試算（USD、Decimal 文字列）。USDC 推奨時は "0" */
  annual_savings_usd: string;
  /** RPC 失敗時のエラーメッセージ。null = 正常取得 */
  error: string | null;
}

/**
 * GET /aave/borrow-rates — GHO / USDC 借入金利比較と最適借入通貨推奨を取得する（viewer 以上）
 */
export async function getBorrowRates(): Promise<BorrowRateComparison> {
  return getJson<BorrowRateComparison>("/api/aave/borrow-rates");
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
  recommended_liquidation_threshold_bps: string; // Decimal 文字列 (M-2 追加)
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

export interface EModeTxData {
  to: string;
  data: string;
  from: string;
  chainId: number;
  value: string;
}

export interface EModeSetResponse {
  category_id: number;
  tx_hash: string | null; // dry_run=False 時、サーバー側署名・送信完了後の実 tx hash
  set_emode_tx: EModeTxData | null; // 後方互換のため残すフィールド。現在は常に null
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
