// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { getJson, postJson } from "./http";

// Type definitions matching backend schemas
export interface AssetAllocation { asset_symbol: string; current_amount_usd: string; current_pct: string; target_pct: string; deviation_pct: string; }
export interface ProposedOperation { asset_symbol: string; operation: string; amount_usd: string; reason: string; }
export interface RebalanceProposal { proposal_id: string; created_at: string; health_factor_before: string | null; total_value_usd: string; allocations: AssetAllocation[]; operations: ProposedOperation[]; estimated_health_factor_after: string | null; max_single_trade_pct: string; confirmation_token: string | null; is_executable: boolean; rejection_reasons: string[]; }
export interface RebalanceResult { proposal_id: string; executed_at: string; operations: unknown[]; health_factor_before: string | null; health_factor_after: string | null; status: string; message: string; }
export interface RebalanceHistoryEntry { proposal_id: string; created_at: string; executed_at: string | null; status: string; total_value_usd: string; operations_count: number; health_factor_before: string | null; health_factor_after: string | null; }
export interface RebalanceStatusResponse { current_allocations: AssetAllocation[]; target_allocations: AssetAllocation[]; health_factor: string | null; total_value_usd: string; deviation_threshold_pct: string; needs_rebalance: boolean; last_rebalance_at: string | null; cooldown_remaining_seconds: number; }

function authHeaders(token: string): HeadersInit { return { Authorization: `Bearer ${token}` }; }

export async function fetchRebalanceStatus(token: string) { return getJson<RebalanceStatusResponse>("/api/aave/rebalance/status", { headers: authHeaders(token) }); }
export async function simulateRebalance(token: string) { return postJson<{ proposal: RebalanceProposal }>("/api/aave/rebalance/simulate", {}, { headers: authHeaders(token) }); }
export async function executeRebalance(token: string, proposalId: string, confirmationToken: string) { return postJson<{ result: RebalanceResult }>("/api/aave/rebalance/execute", { proposal_id: proposalId, confirmation_token: confirmationToken }, { headers: authHeaders(token) }); }
export async function fetchRebalanceHistory(token: string) { return getJson<RebalanceHistoryEntry[]>("/api/aave/rebalance/history", { headers: authHeaders(token) }); }
