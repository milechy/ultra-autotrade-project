// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/admin-proposals.ts

import { getJson } from "./http";

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
