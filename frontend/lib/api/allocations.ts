// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/allocations.ts

import { getJson } from './http'

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

export interface PerformanceResponse {
  /** Total amount allocated to testers (cost basis). */
  total_allocated_usd: number
  /** Current Aave collateral value (total_supply_usd). */
  total_supply_usd: number
  /** Aave Health Factor. Infinity is encoded as 999.0 by the backend. */
  health_factor: number | null
  testers: TesterPerformance[]
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

export async function fetchPerformance(token: string): Promise<PerformanceResponse> {
  return getJson<PerformanceResponse>('/api/partner/performance', {
    headers: authHeaders(token),
  })
}
