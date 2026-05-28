// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/hooks/useWalletBalance.ts
'use client'

import { useEffect, useState } from 'react'
import { fetchWalletBalance, type WalletBalance } from '@/lib/api/wallet_balance'
import { getStoredToken } from '@/lib/auth'

const POLL_INTERVAL_MS = 60_000

/**
 * Partner 自身のウォレット残高 (USDC + ETH on Base mainnet) を 60 秒間隔で取得する hook。
 *
 * - 認証 token が無ければ data=null のまま loading=false
 * - 取得失敗時は data=null
 * - backend 側にも 60 秒 cache があるので二重 cache だが、UI の即時応答性を優先する
 */
export function useWalletBalance(): { data: WalletBalance | null; loading: boolean } {
  const [data, setData] = useState<WalletBalance | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = () => {
      const token = getStoredToken()
      if (!token) {
        setLoading(false)
        return
      }
      fetchWalletBalance(token)
        .then(setData)
        .catch(() => setData(null))
        .finally(() => setLoading(false))
    }

    setLoading(true)
    load()
    const id = setInterval(load, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [])

  return { data, loading }
}
