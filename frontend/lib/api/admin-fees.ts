// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/admin-fees.ts

import { getJson, postJson } from "./http";

export interface AdminFeeUserRow {
  user_id: number;
  username: string;
  email: string;
  tier: string;
  risk_mode: string | null;
  total_management_fee: string;
  total_performance_fee: string;
  total_fee: string;
  last_calculation_date: string | null;
  calculation_count: number;
}

export interface AdminFeeMonthlyEntry {
  id: number;
  user_id: number;
  username: string;
  email: string;
  tier: string;
  risk_mode: string | null;
  aum_snapshot: string;
  management_fee: string;
  performance_fee: string;
  total_fee: string;
  calculation_date: string;
  period_type: string;
}

export interface AdminMonthlyAggregate {
  month: string;
  total_management_fee: string;
  total_performance_fee: string;
  total_fee: string;
  user_count: number;
  entry_count: number;
}

export interface AdminFeeRefundRequest {
  amount: string;
  reason: string;
}

export interface AdminFeeRefundResponse {
  success: boolean;
  user_id: number;
  refund_amount: string;
  reason: string;
  created_at: string;
}

function authHeader(token: string): RequestInit {
  return { headers: { Authorization: `Bearer ${token}` } };
}

export async function listAdminUsersFees(token: string): Promise<AdminFeeUserRow[]> {
  return getJson<AdminFeeUserRow[]>("/api/billing/admin/users", authHeader(token));
}

export async function listAdminMonthlyEntries(
  token: string,
  month: string,
): Promise<AdminFeeMonthlyEntry[]> {
  return getJson<AdminFeeMonthlyEntry[]>(
    `/api/billing/admin/monthly-entries?month=${encodeURIComponent(month)}`,
    authHeader(token),
  );
}

export async function getAdminMonthlySummary(
  token: string,
  month: string,
): Promise<AdminMonthlyAggregate> {
  return getJson<AdminMonthlyAggregate>(
    `/api/billing/admin/monthly-summary?month=${encodeURIComponent(month)}`,
    authHeader(token),
  );
}

export async function createAdminRefund(
  token: string,
  userId: number,
  req: AdminFeeRefundRequest,
): Promise<AdminFeeRefundResponse> {
  return postJson<AdminFeeRefundResponse>(
    `/api/billing/admin/${userId}/refund`,
    req,
    authHeader(token),
  );
}

export function buildCsvExportUrl(token: string, month: string): string {
  const base = process.env.NEXT_PUBLIC_BACKEND_BASE_URL?.replace(/\/$/, "") ?? "";
  return `${base}/api/billing/admin/export-csv?month=${encodeURIComponent(month)}`;
}
