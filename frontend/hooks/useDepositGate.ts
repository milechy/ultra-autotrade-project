// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useEffect, useState } from 'react'
import { SUPPORTED_ASSETS, ASSET_DECIMALS, type SupportedAsset } from '@/lib/constants/assets'

/**
 * $200 USDC 入金ゲート用 hook。
 *
 * 注: P2-onramp PR で `useUsdcBalance` が追加されたら、本 hook は
 *     そちらへ統合する想定。本 PR ではコンフリクト回避のため
 *     自前で簡易実装する。
 *
 * 戻り値:
 *   - locked     : 残高 < threshold なら true
 *   - balanceUsd : 現在の USDC 残高 (USD 換算)
 *   - threshold  : ロック解除に必要な最低額 (USD)
 *   - isLoading  : 残高取得中フラグ
 */
export const DEPOSIT_GATE_THRESHOLD_USD = 200

export type DepositGateState = {
  locked: boolean
  balanceUsd: number
  threshold: number
  isLoading: boolean
}

export { SUPPORTED_ASSETS, ASSET_DECIMALS }
export type { SupportedAsset }

export function useDepositGate(): DepositGateState {
  const [balanceUsd, setBalanceUsd] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)

  useEffect(() => {
    let cancelled = false
    const fetchBalance = async () => {
      try {
        // 本 PR 範囲: 簡易実装。
        // 将来は useUsdcBalance(P2-onramp) または on-chain Multicall に置換。
        // 現状は localStorage に既知の残高があれば採用、無ければ 0 とみなす。
        if (typeof window === 'undefined') return
        const raw = window.localStorage.getItem('uata.usdcBalanceUsd')
        const parsed = raw ? Number(raw) : 0
        if (!cancelled) {
          setBalanceUsd(Number.isFinite(parsed) ? parsed : 0)
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void fetchBalance()
    return () => {
      cancelled = true
    }
  }, [])

  const locked = balanceUsd < DEPOSIT_GATE_THRESHOLD_USD

  return {
    locked,
    balanceUsd,
    threshold: DEPOSIT_GATE_THRESHOLD_USD,
    isLoading,
  }
}
