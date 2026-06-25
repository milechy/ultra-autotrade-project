// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/admin-proposals.ts

import { getJson, postJson } from "./http";

export interface AdminProposal {
  id: number;
  user_id: number;
  username: string | null;
  email: string | null;
  ai_decision_id: number | null;
  operation: string;
  asset: string;
  amount: string;
  amount_usd: string;
  fee_rate: string | null;
  fee_amount: string | null;
  reason: string;
  expected_hf_after: string | null;
  estimated_gas_usd: string | null;
  status: string;
  approved_at: string | null;
  rejected_at: string | null;
  executed_at: string | null;
  tx_hash: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
}

export interface AdminProposalListResponse {
  items: AdminProposal[];
  total: number;
  page: number;
  limit: number;
}

export interface AdminProposalFilters {
  status?: string;
  user_id?: number;
  operation?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  limit?: number;
}

export interface AdminProposalStats {
  pending: number;
  today_approved: number;
  today_rejected: number;
  expired: number;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function fetchAdminProposalStats(
  token: string
): Promise<AdminProposalStats> {
  return await getJson<AdminProposalStats>("/api/proposals/admin/stats", {
    headers: authHeaders(token),
  });
}

export async function listAdminProposals(
  token: string,
  filters: AdminProposalFilters = {}
): Promise<AdminProposalListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.user_id != null) params.set("user_id", String(filters.user_id));
  if (filters.operation) params.set("operation", filters.operation);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.page != null) params.set("page", String(filters.page));
  if (filters.limit != null) params.set("limit", String(filters.limit));

  const qs = params.toString();
  return await getJson<AdminProposalListResponse>(
    `/api/proposals/admin/all${qs ? `?${qs}` : ""}`,
    { headers: authHeaders(token) }
  );
}

export async function approveProposal(
  id: number,
  token: string
): Promise<AdminProposal> {
  return await postJson<AdminProposal>(
    `/api/proposals/${id}/approve`,
    {},
    { headers: authHeaders(token) }
  );
}

export async function rejectProposal(
  id: number,
  token: string
): Promise<AdminProposal> {
  return await postJson<AdminProposal>(
    `/api/proposals/${id}/reject`,
    {},
    { headers: authHeaders(token) }
  );
}

// --- 方式2: パートナー本人署名 (Privy) ---

export interface UnsignedTx {
  to: string;
  data: string;
  from: string;
  chainId: number;
  value: string;
}

export interface PartnerUnsignedTxs {
  proposal_id: number;
  operation: string;
  wallet_address: string;
  approve_tx?: UnsignedTx;
  supply_tx?: UnsignedTx;
  withdraw_tx?: UnsignedTx;
  // 非カストディアル化 (Lido/Pendle)。partner が Privy 本人署名する未署名 tx。
  stake_tx?: UnsignedTx; // STAKE_ETH (Lido) のみ
  buy_pt_tx?: UnsignedTx; // BUY_PT (Pendle) のみ
}

/** 未署名 tx データをバックエンドから取得する (サーバー鍵で署名しない)。 */
export async function buildPartnerTx(
  id: number,
  token: string
): Promise<PartnerUnsignedTxs> {
  return await getJson<PartnerUnsignedTxs>(`/api/proposals/${id}/build-tx`, {
    headers: authHeaders(token),
  });
}

/** Privy で署名・送信した最終 tx_hash をバックエンドに報告する。 */
export async function submitPartnerTx(
  id: number,
  txHash: string,
  walletAddress: string,
  token: string
): Promise<AdminProposal> {
  return await postJson<AdminProposal>(
    `/api/proposals/${id}/submit-tx`,
    { tx_hash: txHash, wallet_address: walletAddress },
    { headers: authHeaders(token) }
  );
}
