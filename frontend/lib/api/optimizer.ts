// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/optimizer.ts
//
// AI Optimizer API クライアント。
// backend: POST /api/ai/optimizer/recommend（投資額・リスクモード・保有日数 →
// 戦略比較 + ポートフォリオ配分推奨）。Decimal はバックエンドから文字列で返る。

import { postJson } from "./http"

export type RiskMode = "conservative" | "balanced" | "aggressive"

export interface OptimizerRequestBody {
  investment_usd: number
  risk_mode: RiskMode
  holding_days: number
}

export type RecommendationLevel = "STRONG_BUY" | "BUY" | "HOLD" | "AVOID"

export interface NetBenefitResult {
  protocol: string
  asset: string
  expected_net_benefit: string // Decimal 文字列（USD・年換算）
  gross_yield: string
  total_cost: string
  risk_adjusted_yield: string
  expected_apy: string // %（Decimal 文字列）
  rank: number
  recommendation: RecommendationLevel
}

export interface AllocationEntry {
  protocol: string
  asset: string
  allocation_pct: string // 0-100（Decimal 文字列）
  amount_usd: string
  expected_apy: string
}

export interface AllocationRecommendation {
  allocations: AllocationEntry[]
  total_expected_apy: string
  total_risk_score: string
  explanation: string
}

export interface StrategyComparison {
  candidates: NetBenefitResult[]
  recommended: NetBenefitResult
  idle_benefit: string
  comparison_timestamp: string
}

export interface OptimizerResponse {
  comparison: StrategyComparison
  allocation: AllocationRecommendation
  report: string
}

/**
 * POST /api/ai/optimizer/recommend — 戦略比較 + 最適配分推奨を取得する。
 *
 * base URL 未設定時は Next proxy（app/api/ai/[...path]）が backend へ転送する。
 */
export async function recommendStrategy(
  req: OptimizerRequestBody,
): Promise<OptimizerResponse> {
  return postJson<OptimizerResponse>("/api/ai/optimizer/recommend", req)
}
