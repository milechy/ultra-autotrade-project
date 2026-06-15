// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/yield.ts
/**
 * Yield Optimizer API クライアント。
 * Privy Earn / Morpho Vaults アイドル資本自動運用エンドポイント。
 */

import { getJson, postJson } from "./http";

// ---- Types ----

export interface MorphoVault {
  vault_address: string;
  name: string;
  /** 年利 (Decimal 文字列, 例: "0.0523" = 5.23%) */
  apy: string;
  /** TVL USD (Decimal 文字列) */
  tvl_usd: string;
}

export interface YieldPosition {
  vault_address: string;
  /** 預け入れ USDC 数量 (Decimal 文字列) */
  deposited_amount: string;
  /** 現在価値 USDC (Decimal 文字列) */
  current_value: string;
  /** 獲得利息 USD (Decimal 文字列) */
  earned_usd: string;
  last_updated: string | null;
}

export interface VaultListResponse {
  vaults: MorphoVault[];
  best_apy_vault: MorphoVault | null;
  fetched_at: string;
}

export interface PositionListResponse {
  positions: YieldPosition[];
  total_deposited_usdc: string;
  total_earned_usd: string;
  fetched_at: string;
}

export interface IdleCapitalReport {
  bybit_free_usdc: string;
  deployed_amount: string;
  idle_amount: string;
  should_deploy: boolean;
  threshold: string;
  reason: string | null;
  checked_at: string;
}

export interface TxResult {
  tx_hash: string;
  vault_address: string;
  operation: string;
  amount: string;
  submitted_at: string;
}

export interface DepositRequest {
  vault_address: string;
  /** 入金 USDC 数量 (正の値文字列) */
  amount_usdc: string;
}

export interface WithdrawRequest {
  vault_address: string;
  /** 出金 USDC 数量 (正の値文字列) */
  amount: string;
}

// ---- API 関数 ----

/**
 * GET /api/yield-optimizer/vaults — Vault 一覧取得 (viewer 以上)
 */
export async function getVaults(): Promise<VaultListResponse> {
  return getJson<VaultListResponse>("/api/yield-optimizer/vaults");
}

/**
 * GET /api/yield-optimizer/positions — ポジション一覧取得 (viewer 以上)
 */
export async function getPositions(): Promise<PositionListResponse> {
  return getJson<PositionListResponse>("/api/yield-optimizer/positions");
}

/**
 * GET /api/yield-optimizer/idle-report — アイドル資本レポート (viewer 以上)
 */
export async function getIdleReport(): Promise<IdleCapitalReport> {
  return getJson<IdleCapitalReport>("/api/yield-optimizer/idle-report");
}

/**
 * POST /api/yield-optimizer/deposit — Morpho Vault 入金 (admin 専用)
 *
 * HUMAN-REVIEW-REQUIRED: 資金移動操作。
 */
export async function depositToVault(req: DepositRequest): Promise<TxResult> {
  return postJson<TxResult>("/api/yield-optimizer/deposit", req);
}

/**
 * POST /api/yield-optimizer/withdraw — Morpho Vault 出金 (admin 専用)
 *
 * HUMAN-REVIEW-REQUIRED: 資金移動操作。
 */
export async function withdrawFromVault(req: WithdrawRequest): Promise<TxResult> {
  return postJson<TxResult>("/api/yield-optimizer/withdraw", req);
}
