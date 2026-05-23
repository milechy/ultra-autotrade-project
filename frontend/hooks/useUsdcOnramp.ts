// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useCallback, useState } from 'react'
import { useFundWallet, usePrivy } from '@privy-io/react-auth'

/**
 * Privy useFundWallet を Base / USDC で呼ぶラッパー hook。
 *
 * - chain: Base mainnet (chainId 8453)
 * - asset: USDC (Base 上の USDC contract)
 *
 * 完了時に backend `/api/users/actions` へ `onramp_completed` を記録する。
 * バックエンド側 user_actions テーブルが未マイグレーションでも例外で
 * UX が崩れないよう、POST 失敗は console.warn でログするのみ。
 */

// Base mainnet USDC contract (native USDC, not USDbC)
// https://www.circle.com/blog/native-usdc-now-available-on-base
const USDC_BASE_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913' as const
const BASE_CHAIN_ID = 8453

export interface UseUsdcOnrampResult {
  openOnramp: (args: { amount: number }) => Promise<void>
  isLoading: boolean
  error: Error | null
}

async function recordOnrampAction(amountUsd: number): Promise<void> {
  try {
    const res = await fetch('/api/users/actions', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action_type: 'onramp_completed',
        target_type: 'wallet',
        context_json: {
          chain_id: BASE_CHAIN_ID,
          asset: 'USDC',
          asset_address: USDC_BASE_ADDRESS,
          amount_usd: amountUsd,
        },
      }),
    })
    if (!res.ok) {
      // user_actions テーブル未作成 (P0-6 未マージ) の段階では 404/500 もありうる
      // eslint-disable-next-line no-console
      console.warn('[useUsdcOnramp] POST /api/users/actions failed', res.status)
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[useUsdcOnramp] POST /api/users/actions threw', err)
  }
}

export function useUsdcOnramp(): UseUsdcOnrampResult {
  const { user } = usePrivy()
  const { fundWallet } = useFundWallet({
    onUserExited: ({ fundingMethod }) => {
      // fundingMethod が undefined のとき = ユーザーがキャンセル
      if (fundingMethod) {
        // 入金完了 callback (Privy 側で完了判定された場合)
        // amount は openOnramp 時に handler 内で再記録するので、ここでは何もしない
      }
    },
  })

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const openOnramp = useCallback(
    async ({ amount }: { amount: number }) => {
      setError(null)
      setIsLoading(true)
      try {
        const walletAddress = user?.wallet?.address
        if (!walletAddress) {
          throw new Error('Privy wallet not connected')
        }
        await fundWallet(walletAddress, {
          chain: { id: BASE_CHAIN_ID },
          asset: { erc20: USDC_BASE_ADDRESS },
          amount: String(amount),
        })
        // Privy は同期的にモーダルを開くだけで完了は onUserExited で通知される。
        // 完了判定の代わりに、ユーザーが UI を閉じた直後に best-effort で記録する。
        await recordOnrampAction(amount)
      } catch (err) {
        const e = err instanceof Error ? err : new Error(String(err))
        setError(e)
        throw e
      } finally {
        setIsLoading(false)
      }
    },
    [fundWallet, user?.wallet?.address],
  )

  return { openOnramp, isLoading, error }
}
