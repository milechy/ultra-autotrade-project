// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/admin-transactions.ts
/**
 * 管理者向け取引履歴 API クライアント。
 * GET /api/admin/transactions
 */

import { apiFetch } from './client'

export interface AdminTransaction {
  id: number
  user_id: number
  wallet_address: string | null
  operation: string
  asset: string
  amount: string
  amount_usd: string
  tx_hash: string | null
  chain: string
  status: string
  ai_decision_id: number | null
  gas_used: string | null
  gas_price_gwei: string | null
  is_dry_run: boolean
  created_at: string
  updated_at: string
}

export interface AdminTransactionListResponse {
  items: AdminTransaction[]
  total: number
  limit: number
  offset: number
}

export interface AdminTransactionFilters {
  limit?: number
  offset?: number
  user_id?: number
  wallet_address?: string
  operation?: string
  tx_status?: string
  date_from?: string
  date_to?: string
}

export async function fetchAdminTransactions(
  filters: AdminTransactionFilters
): Promise<AdminTransactionListResponse> {
  const params = new URLSearchParams()
  if (filters.limit != null) params.set('limit', String(filters.limit))
  if (filters.offset != null) params.set('offset', String(filters.offset))
  if (filters.user_id != null) params.set('user_id', String(filters.user_id))
  if (filters.wallet_address) params.set('wallet_address', filters.wallet_address)
  if (filters.operation) params.set('operation', filters.operation)
  if (filters.tx_status) params.set('tx_status', filters.tx_status)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  const qs = params.toString()
  return apiFetch<AdminTransactionListResponse>(
    `/api/admin/transactions${qs ? `?${qs}` : ''}`
  )
}
