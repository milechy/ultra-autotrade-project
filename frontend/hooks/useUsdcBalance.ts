// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createPublicClient,
  http,
  parseAbiItem,
  type Address,
  type Log,
} from 'viem'
import { base } from 'viem/chains'
import { usePrivy } from '@privy-io/react-auth'

/**
 * USDC.balanceOf を viem readContract で取得する hook。
 *
 * 2 層の更新経路:
 *   1. 即時 (indexed): `watchContractEvent` で USDC Transfer event の
 *      `to == user` を listen し、検知したら即 refetch。
 *      - 失敗時 (例: http transport で WebSocket が無い、RPC が
 *        eth_getLogs subscription を拒否) は warn ログを残して polling のみで継続。
 *   2. fallback (polling): 30 秒間隔の setInterval で balanceOf を再取得。
 *      - 以前は 15 秒だったが、indexed 経路ができたので 30 秒に緩和。
 *
 * - chain: Base mainnet
 * - USDC contract: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 (decimals = 6)
 *
 * 戻り値の balanceUsd は decimals 6 を考慮した USD 換算値 (1 USDC ≒ 1 USD)。
 */

const USDC_BASE_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913' as const
const USDC_DECIMALS = 6
const POLL_INTERVAL_MS = 30_000
const MAX_RETRY = 3
const RETRY_BACKOFF_MS = 2_000

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

// USDC Transfer event signature
const USDC_TRANSFER_EVENT = parseAbiItem(
  'event Transfer(address indexed from, address indexed to, uint256 value)',
)

const publicClient = createPublicClient({
  chain: base,
  transport: http(),
})

export interface UseUsdcBalanceResult {
  balance: bigint
  balanceUsd: number
  isLoading: boolean
  error: Error | null
  refetch: () => void
}

export function useUsdcBalance(): UseUsdcBalanceResult {
  const { user } = usePrivy()
  const address = (user?.wallet?.address ?? null) as Address | null

  const [balance, setBalance] = useState<bigint>(0n)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [error, setError] = useState<Error | null>(null)

  // 最新の address を保持 (closure 経由でなく ref で読む)
  const addressRef = useRef<Address | null>(null)
  addressRef.current = address

  const fetchBalance = useCallback(async () => {
    const addr = addressRef.current
    if (!addr) {
      setBalance(0n)
      return
    }
    setIsLoading(true)
    let lastErr: unknown = null
    for (let attempt = 0; attempt < MAX_RETRY; attempt++) {
      try {
        const result = (await publicClient.readContract({
          address: USDC_BASE_ADDRESS,
          abi: ERC20_BALANCE_OF_ABI,
          functionName: 'balanceOf',
          args: [addr],
        })) as bigint
        setBalance(result)
        setError(null)
        setIsLoading(false)
        return
      } catch (err) {
        lastErr = err
        if (attempt < MAX_RETRY - 1) {
          await new Promise((r) =>
            setTimeout(r, RETRY_BACKOFF_MS * (attempt + 1)),
          )
        }
      }
    }
    // 全リトライ失敗
    const e =
      lastErr instanceof Error ? lastErr : new Error(String(lastErr ?? 'unknown'))
    // eslint-disable-next-line no-console
    console.warn('[useUsdcBalance] readContract failed after retries', e)
    setError(e)
    setIsLoading(false)
  }, [])

  // 初回取得 + 30s polling (fallback)
  useEffect(() => {
    if (!address) return
    void fetchBalance()
    const id = setInterval(() => {
      void fetchBalance()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [address, fetchBalance])

  // indexed 経路: USDC Transfer (to=user) を WebSocket subscribe して即 refetch
  useEffect(() => {
    if (!address) return
    let unwatch: (() => void) | null = null
    try {
      unwatch = publicClient.watchContractEvent({
        address: USDC_BASE_ADDRESS,
        abi: [USDC_TRANSFER_EVENT],
        eventName: 'Transfer',
        // args.to == user のみフィルタ (RPC 側で indexed フィルタが効く)
        args: { to: address },
        onLogs: (_logs: Log[]) => {
          // 1 回でも Transfer to=user を観測したら balance を即取り直す
          void fetchBalance()
        },
        onError: (err: Error) => {
          // http transport では eth_newFilter polling fallback が viem 側で
          // 行われる。それすら拒否される RPC では onError が呼ばれる。
          // 致命ではなく polling fallback に委ねる。
          // eslint-disable-next-line no-console
          console.warn(
            '[useUsdcBalance] watchContractEvent error (fallback to polling)',
            err,
          )
        },
      })
    } catch (err) {
      // viem が subscription を作れない (transport 非対応) ケース。
      // polling のみで継続。
      // eslint-disable-next-line no-console
      console.warn(
        '[useUsdcBalance] watchContractEvent unsupported (fallback to polling)',
        err,
      )
    }
    return () => {
      if (unwatch) {
        try {
          unwatch()
        } catch {
          // unwatch 失敗は無視
        }
      }
    }
  }, [address, fetchBalance])

  const balanceUsd = Number(balance) / 10 ** USDC_DECIMALS

  return {
    balance,
    balanceUsd,
    isLoading,
    error,
    refetch: fetchBalance,
  }
}
