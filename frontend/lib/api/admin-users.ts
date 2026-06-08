// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/admin-users.ts
/**
 * 管理者向けユーザー運用状況 API クライアント。
 * GET  /api/admin/users
 * POST /api/admin/users/{id}/pause
 * POST /api/admin/users/{id}/resume
 */

import { apiFetch, apiPost } from './client'

export interface AdminUserPosition {
  asset: string
  supplied: number
  borrowed: number
  usdValue: number
}

export interface AdminUserHFPoint {
  date: string
  hf: number
}

export interface AdminUserRecentTrade {
  id: string
  type: string
  asset: string
  amount: number
  timestamp: string
}

export interface AdminUserRecentDecision {
  id: string
  action: string
  confidence: number
  timestamp: string
}

export interface AdminUserDetail {
  id: string
  address: string
  registeredAt: string
  aum: number
  lastActivity: string
  riskMode: 'conservative' | 'balanced' | 'aggressive'
  status: 'NORMAL' | 'WARNING' | 'DANGER'
  isPaused: boolean
  positions: AdminUserPosition[]
  healthFactor: number
  hfHistory: AdminUserHFPoint[]
  recentTrades: AdminUserRecentTrade[]
  recentDecisions: AdminUserRecentDecision[]
}

export async function fetchAdminUsers(): Promise<AdminUserDetail[]> {
  return apiFetch<AdminUserDetail[]>('/api/admin/users')
}

export async function pauseAdminUser(userId: string): Promise<void> {
  await apiPost<unknown>(`/api/admin/users/${userId}/pause`, null)
}

export async function resumeAdminUser(userId: string): Promise<void> {
  await apiPost<unknown>(`/api/admin/users/${userId}/resume`, null)
}
