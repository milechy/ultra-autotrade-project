// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useCallback, useEffect, useState } from 'react'
import { createPublicClient, http, type Address } from 'viem'
import { base } from 'viem/chains'
import { usePrivy } from '@privy-io/react-auth'

/**
 * USDC.balanceOf を viem readContract で取得する hook。
 *
 * - chain: Base mainnet
 * - USDC contract: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 (decimals = 6)
 * - polling: 15 秒間隔 (setInterval)
 *
 * 戻り値の balanceUsd は decimals 6 を考慮した USD 換算値 (1 USDC ≒ 1 USD)。
 */

const USDC_BASE_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913' as const
const USDC_DECIMALS = 6
const POLL_INTERVAL_MS = 15_000

const ERC20_BALANCE_OF_ABI = [
  {
    constant: true,
    inputs: [{ name: '_owner', type: 'address' }],
    name: 'balanceOf',
    outputs: [{ name: 'balance', type: 'uint256' }],
    type: 'function',
    stateMutability: 'view',
  },
] as const

const publicClient = createPublicClient({
  chain: base,
  transport: http(),
})

export interface UseUsdcBalanceResult {
  balance: bigint
  balanceUsd: number
  isLoading: boolean
  refetch: () => void
}

export function useUsdcBalance(): UseUsdcBalanceResult {
  const { user } = usePrivy()
  const address = (user?.wallet?.address ?? null) as Address | null

  const [balance, setBalance] = useState<bigint>(0n)
  const [isLoading, setIsLoading] = useState<boolean>(false)

  const fetchBalance = useCallback(async () => {
    if (!address) {
      setBalance(0n)
      return
    }
    setIsLoading(true)
    try {
      const result = (await publicClient.readContract({
        address: USDC_BASE_ADDRESS,
        abi: ERC20_BALANCE_OF_ABI,
        functionName: 'balanceOf',
        args: [address],
      })) as bigint
      setBalance(result)
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[useUsdcBalance] readContract failed', err)
    } finally {
      setIsLoading(false)
    }
  }, [address])

  // 初回取得 + 15s polling
  useEffect(() => {
    if (!address) return
    void fetchBalance()
    const id = setInterval(() => {
      void fetchBalance()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [address, fetchBalance])

  const balanceUsd = Number(balance) / 10 ** USDC_DECIMALS

  return {
    balance,
    balanceUsd,
    isLoading,
    refetch: fetchBalance,
  }
}
