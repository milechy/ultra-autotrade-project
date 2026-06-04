// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/wallet_balance.ts

import { getJson } from './http'

// ---- Types ----

export interface WalletBalance {
  wallet_address: string
  chain: 'base'
  /** ETH 残高 (ether 単位)。Decimal を string で受ける。 */
  eth_balance: string
  /** ETH × ETH/USD price */
  eth_usd_value: string
  /** 1 ETH = ? USD */
  eth_usd_price: string
  /** USDC 残高 (USDC 単位) */
  usdc_balance: string
  /** USDC × 1.00 (1:1 simplification) */
  usdc_usd_value: string
  /** eth_usd_value + usdc_usd_value */
  total_usd: string
  /** ISO datetime */
  fetched_at: string
  /** 0 if fresh, else seconds since fetched */
  cache_age_seconds: number
  /** true if RPC or price fallback was triggered */
  fallback_used: boolean
}

// ---- Helpers ----

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

// ---- API Functions ----

export async function fetchWalletBalance(token: string): Promise<WalletBalance> {
  return getJson<WalletBalance>('/api/partner/wallet-balance', {
    headers: authHeaders(token),
  })
}
