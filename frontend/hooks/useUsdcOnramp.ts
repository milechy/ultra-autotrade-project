// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useCallback, useRef, useState } from 'react'
import { useFundWallet, usePrivy } from '@privy-io/react-auth'
import { createPublicClient, http, type Address } from 'viem'
import { base } from 'viem/chains'

/**
 * Privy useFundWallet を Base / USDC で呼ぶラッパー hook。
 *
 * - chain: Base mainnet (chainId 8453)
 * - asset: USDC (Base 上の USDC contract)
 *
 * `onUserExited` callback で、入金前後の USDC 残高差分を verbatim 計算し、
 * 実 amount として backend `/api/users/actions` (`onramp_completed`) に
 * 記録する (logUserAction 相当)。
 *
 * - 入金前: openOnramp 呼び出し直後に balanceOf を取得し ref に保存
 * - 入金後: onUserExited で再度 balanceOf を取り差分を amount_usd として記録
 * - 差分が 0 以下 (cancel or 未着金) のときも fundingMethod を context に残す
 * - バックエンド側 user_actions テーブル未マイグレーションでも UX を壊さない
 *   よう、POST 失敗は console.warn でログするのみ。
 */

// Base mainnet USDC contract (native USDC, not USDbC)
// https://www.circle.com/blog/native-usdc-now-available-on-base
const USDC_BASE_ADDRESS = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913' as const
const BASE_CHAIN_ID = 8453
const USDC_DECIMALS = 6
const DEFAULT_AMOUNT_USD = 250

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

// shared (read-only) client for balance diff.
const onrampPublicClient = createPublicClient({
  chain: base,
  transport: http(),
})

export interface UseUsdcOnrampOptions {
  /** Privy modal で初期表示する入金額 (USD)。default 250。 */
  defaultAmount?: number
}

export interface OnrampCompletedContext {
  chain_id: number
  asset: 'USDC'
  asset_address: string
  amount_usd: number // 残高差分から計算した実 amount (USD 換算)
  requested_amount_usd: number // UI 上 user が要求した amount
  fund_method?: string | null // Privy 側の fundingMethod (cancel 時は null)
  tx_hash?: string | null
}

export interface UseUsdcOnrampResult {
  openOnramp: (args?: { amount?: number }) => Promise<void>
  isLoading: boolean
  error: Error | null
  /** 最後に実 amount として記録した USD 値 (cancel 時は 0)。 */
  lastAmount: number
}

async function readUsdcBalance(address: Address): Promise<bigint> {
  try {
    const result = (await onrampPublicClient.readContract({
      address: USDC_BASE_ADDRESS,
      abi: ERC20_BALANCE_OF_ABI,
      functionName: 'balanceOf',
      args: [address],
    })) as bigint
    return result
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[useUsdcOnramp] balanceOf failed', err)
    return 0n
  }
}

function rawToUsd(raw: bigint): number {
  // USDC は 6 decimals。Number 化で誤差が出る桁数 (>= 1e15) は実運用上来ない。
  return Number(raw) / 10 ** USDC_DECIMALS
}

async function logUserAction(
  actionType: 'onramp_completed' | 'onramp_cancelled',
  context: OnrampCompletedContext,
): Promise<void> {
  try {
    const res = await fetch('/api/users/actions', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action_type: actionType,
        target_type: 'wallet',
        context_json: context,
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

export function useUsdcOnramp(
  options: UseUsdcOnrampOptions = {},
): UseUsdcOnrampResult {
  const { defaultAmount = DEFAULT_AMOUNT_USD } = options

  const { user } = usePrivy()
  const walletAddress = (user?.wallet?.address ?? null) as Address | null

  // openOnramp 呼び出し直前の残高 (raw, decimals 6)
  const balanceBeforeRef = useRef<bigint>(0n)
  // 最後に開いた要求 amount
  const requestedAmountRef = useRef<number>(defaultAmount)

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [lastAmount, setLastAmount] = useState<number>(0)

  const { fundWallet } = useFundWallet({
    onUserExited: async ({ fundingMethod }: { fundingMethod?: string }) => {
      // ユーザーが Privy モーダルを閉じた直後に呼ばれる。
      // - fundingMethod === undefined → ユーザーがキャンセル
      // - fundingMethod !== undefined → 入金フロー何かしら通過 (ただし
      //   on-chain 着金は遅延するので balance 差分が 0 の場合もある)
      try {
        if (!walletAddress) {
          return
        }
        const balanceAfter = await readUsdcBalance(walletAddress)
        const deltaRaw = balanceAfter - balanceBeforeRef.current
        const deltaUsd = deltaRaw > 0n ? rawToUsd(deltaRaw) : 0
        setLastAmount(deltaUsd)

        const actionType =
          fundingMethod && deltaUsd > 0
            ? 'onramp_completed'
            : fundingMethod
              ? 'onramp_completed' // method 通過したが着金遅延 → 後で再 reconcile
              : 'onramp_cancelled'

        await logUserAction(actionType, {
          chain_id: BASE_CHAIN_ID,
          asset: 'USDC',
          asset_address: USDC_BASE_ADDRESS,
          amount_usd: deltaUsd,
          requested_amount_usd: requestedAmountRef.current,
          fund_method: fundingMethod ?? null,
          tx_hash: null,
        })
      } catch (err) {
        const e = err instanceof Error ? err : new Error(String(err))
        setError(e)
      } finally {
        setIsLoading(false)
      }
    },
  })

  const openOnramp = useCallback(
    async (args?: { amount?: number }) => {
      const amount = args?.amount ?? defaultAmount
      setError(null)
      setIsLoading(true)
      requestedAmountRef.current = amount
      try {
        if (!walletAddress) {
          throw new Error('Privy wallet not connected')
        }
        // 入金前残高を ref に記録
        balanceBeforeRef.current = await readUsdcBalance(walletAddress)

        await fundWallet(walletAddress, {
          chain: { id: BASE_CHAIN_ID },
          asset: { erc20: USDC_BASE_ADDRESS },
          amount: String(amount),
        })
        // 注意: fundWallet は同期的にモーダルを開くだけで、完了は onUserExited
        // で通知される。setIsLoading(false) は onUserExited 側で行う。
      } catch (err) {
        const e = err instanceof Error ? err : new Error(String(err))
        setError(e)
        setIsLoading(false)
        throw e
      }
    },
    [fundWallet, walletAddress, defaultAmount],
  )

  return { openOnramp, isLoading, error, lastAmount }
}
