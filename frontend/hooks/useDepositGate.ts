// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPublicClient, http, erc20Abi, type Address } from 'viem'
import { base } from 'viem/chains'
import { usePrivy } from '@privy-io/react-auth'
import {
  SUPPORTED_ASSETS,
  ASSET_DECIMALS,
  ASSET_ADDRESSES,
  type SupportedAsset,
} from '@/lib/constants/assets'

/**
 * $200 USDC 入金ゲート用 hook。
 *
 * 実装:
 *   - viem `createPublicClient` + `readContract` で USDC.balanceOf(user) を Base から直接取得
 *   - user address は `usePrivy().user.linkedAccounts` から embedded wallet を抽出
 *   - 15s polling、refetch/error 状態を提供
 *
 * Phase 2 で `useUsdcBalance`(P2-onramp)等の共通 hook が整備されたら
 * そちらに統合される想定。
 *
 * 戻り値:
 *   - locked     : 残高 < threshold なら true
 *   - balanceUsd : 現在の USDC 残高 (USD 換算)
 *   - threshold  : ロック解除に必要な最低額 (USD)
 *   - isLoading  : 残高取得中フラグ (初回のみ true)
 *   - error      : 取得失敗時のエラー
 *   - refetch    : 明示的に再取得する関数
 */
export const DEPOSIT_GATE_THRESHOLD_USD = 200
export const DEPOSIT_GATE_POLL_INTERVAL_MS = 15_000

export type DepositGateState = {
  locked: boolean
  balanceUsd: number
  threshold: number
  isLoading: boolean
  error: Error | null
  refetch: () => void
}

export { SUPPORTED_ASSETS, ASSET_DECIMALS, ASSET_ADDRESSES }
export type { SupportedAsset }

const USDC_ASSET: SupportedAsset = 'USDC'

/**
 * Privy の linkedAccounts から最初の embedded wallet address を抽出する。
 * 該当が無ければ通常の wallet account を fallback として返す。
 */
function extractEmbeddedWalletAddress(
  linkedAccounts: ReadonlyArray<unknown> | undefined,
): Address | null {
  if (!linkedAccounts || linkedAccounts.length === 0) return null

  // type guard: Privy の LinkedAccountWithMetadata は type + walletClientType を持つ
  type WalletAccountLike = {
    type?: string
    walletClientType?: string
    address?: string
  }

  const accounts = linkedAccounts as ReadonlyArray<WalletAccountLike>

  // 1) embedded wallet 優先
  const embedded = accounts.find(
    (a) => a?.type === 'wallet' && a?.walletClientType === 'privy' && typeof a?.address === 'string',
  )
  if (embedded?.address) {
    return embedded.address as Address
  }

  // 2) その他の wallet(injected 等)を fallback
  const wallet = accounts.find(
    (a) => a?.type === 'wallet' && typeof a?.address === 'string',
  )
  if (wallet?.address) {
    return wallet.address as Address
  }

  return null
}

let cachedClient: ReturnType<typeof createPublicClient> | null = null

function getPublicClient() {
  if (cachedClient) return cachedClient
  const rpcUrl = process.env.NEXT_PUBLIC_BASE_RPC_URL || 'https://mainnet.base.org'
  cachedClient = createPublicClient({
    chain: base,
    transport: http(rpcUrl),
  })
  return cachedClient
}

export function useDepositGate(): DepositGateState {
  const { user, ready, authenticated } = usePrivy()

  const address = useMemo<Address | null>(
    () => extractEmbeddedWalletAddress(user?.linkedAccounts),
    [user?.linkedAccounts],
  )

  const [balanceUsd, setBalanceUsd] = useState<number>(0)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<Error | null>(null)

  // refetch を安定化するための tick state
  const [tick, setTick] = useState<number>(0)
  const mountedRef = useRef<boolean>(true)

  const refetch = useCallback(() => {
    setTick((t) => t + 1)
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    // Privy 初期化前 or 未認証 or address 未確定 → 読まずに loading false
    if (!ready) {
      setIsLoading(true)
      return
    }
    if (!authenticated || !address) {
      setBalanceUsd(0)
      setError(null)
      setIsLoading(false)
      return
    }

    let cancelled = false

    const fetchBalance = async () => {
      try {
        const client = getPublicClient()
        const raw = (await client.readContract({
          address: ASSET_ADDRESSES[USDC_ASSET],
          abi: erc20Abi,
          functionName: 'balanceOf',
          args: [address],
        })) as bigint

        if (cancelled || !mountedRef.current) return

        const decimals = ASSET_DECIMALS[USDC_ASSET]
        const denom = 10 ** decimals
        // 6 decimals + JS Number で USDC 残高表現可能(最大 ~9e9 USD まで安全)
        const usd = Number(raw) / denom
        setBalanceUsd(Number.isFinite(usd) ? usd : 0)
        setError(null)
      } catch (err) {
        if (cancelled || !mountedRef.current) return
        setError(err instanceof Error ? err : new Error(String(err)))
      } finally {
        if (!cancelled && mountedRef.current) {
          setIsLoading(false)
        }
      }
    }

    // 初回 + tick 変更時 + polling で起動
    setIsLoading(true)
    void fetchBalance()
    const id = setInterval(() => {
      void fetchBalance()
    }, DEPOSIT_GATE_POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [ready, authenticated, address, tick])

  const locked = balanceUsd < DEPOSIT_GATE_THRESHOLD_USD

  return {
    locked,
    balanceUsd,
    threshold: DEPOSIT_GATE_THRESHOLD_USD,
    isLoading,
    error,
    refetch,
  }
}
