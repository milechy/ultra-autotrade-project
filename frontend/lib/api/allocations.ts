// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/allocations.ts

import { getJson, postJson, putJson, deleteJson } from './http'

// ---- Types ----

export interface Allocation {
  id: number
  tester_name: string
  allocated_amount_usd: number
  current_value_usd: number
  pnl_usd: number
  /** Already converted to % by backend. Do NOT divide by 100 again. */
  pnl_percentage: number
  allocated_at: string
  notes?: string | null
}

export interface TesterPerformance {
  tester_name: string
  user_id?: number | null
  allocated_amount_usd: number
  current_value_usd: number
  pnl_usd: number
  /** Already converted to % by backend. */
  pnl_percentage: number
}

export interface PerformanceSummary {
  total_aum_usd: number
  total_pnl_usd: number
  /** Already converted to % by backend. */
  total_pnl_percentage: number
  tester_count: number
  health_factor: number | null
}

export interface PerformanceResponse {
  summary: PerformanceSummary
  testers: TesterPerformance[]
}

export interface CreateAllocationData {
  tester_name: string
  allocated_amount_usd: number
  notes?: string
}

export interface UpdateAllocationData {
  tester_name?: string
  allocated_amount_usd?: number
  notes?: string
}

// ---- Helpers ----

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

// ---- API Functions ----

export async function fetchAllocations(token: string): Promise<Allocation[]> {
  return getJson<Allocation[]>('/api/partner/allocations', {
    headers: authHeaders(token),
  })
}

export async function createAllocation(
  token: string,
  data: CreateAllocationData
): Promise<Allocation> {
  return postJson<Allocation>('/api/partner/allocations', data, {
    headers: authHeaders(token),
  })
}

export async function updateAllocation(
  token: string,
  id: number,
  data: UpdateAllocationData
): Promise<Allocation> {
  return putJson<Allocation>(`/api/partner/allocations/${id}`, data, {
    headers: authHeaders(token),
  })
}

export async function deleteAllocation(token: string, id: number): Promise<void> {
  return deleteJson<void>(`/api/partner/allocations/${id}`, {
    headers: authHeaders(token),
  })
}

export async function fetchPerformance(token: string): Promise<PerformanceResponse> {
  return getJson<PerformanceResponse>('/api/partner/performance', {
    headers: authHeaders(token),
  })
}
