// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/aave.ts
/**
 * Aave 関連 API クライアント
 * - getStressTest(): GET /api/aave/stress-test
 * - getPoolHealth(): GET /api/aave/pool-health
 */

import { getJson } from "./http";

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
