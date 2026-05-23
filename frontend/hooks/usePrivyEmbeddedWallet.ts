// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

/**
 * usePrivyEmbeddedWallet
 * ----------------------
 * P1 (privy-embedded-wallet-mvp):
 * Privy `usePrivy()` から `user.linkedAccounts` を走査して embedded wallet を
 * 取り出し、viem の WalletClient を生成して返す hook。
 *
 * - chain は Base mainnet (8453) 固定。RPC URL は `NEXT_PUBLIC_BASE_RPC_URL` から取得。
 * - 未認証 / embedded wallet 未付与 / Privy 未設定環境では
 *   `{ address: null, walletClient: null, isReady: false }` を返す。
 *
 * NOTE: 実 transaction 送信時は Privy が提供する EIP-1193 provider を transport に
 *       差し込む必要があるが、MVP では address + chain/transport まで提供して、
 *       呼び出し側で `useWallets()` から provider を解決する想定。
 *       (delegated signing PoC は P3 で扱う)
 */

import { useMemo } from 'react'
import { usePrivy } from '@privy-io/react-auth'
import { base } from 'viem/chains'
import {
  createWalletClient,
  http,
  type Address,
  type WalletClient,
} from 'viem'

const BASE_RPC_URL = process.env.NEXT_PUBLIC_BASE_RPC_URL || ''

export interface PrivyEmbeddedWalletState {
  /** Embedded wallet の checksum address (未付与時 null) */
  address: Address | null
  /** viem WalletClient (Base mainnet 固定、未付与時 null) */
  walletClient: WalletClient | null
  /** 認証済み & embedded wallet 取得済みなら true */
  isReady: boolean
}

/**
 * `usePrivy().user.linkedAccounts` から Privy 製の embedded wallet を 1 件返す。
 * Embedded wallet の判定基準は `type === 'wallet'` かつ `walletClientType === 'privy'`。
 */
function pickEmbeddedWalletAddress(
  linkedAccounts: ReadonlyArray<unknown> | undefined,
): Address | null {
  if (!linkedAccounts) return null
  for (const account of linkedAccounts) {
    if (!account || typeof account !== 'object') continue
    const acct = account as Record<string, unknown>
    if (acct.type !== 'wallet') continue
    if (acct.walletClientType !== 'privy') continue
    const addr = acct.address
    if (typeof addr === 'string' && addr.startsWith('0x')) {
      return addr as Address
    }
  }
  return null
}

export function usePrivyEmbeddedWallet(): PrivyEmbeddedWalletState {
  const { ready, authenticated, user } = usePrivy()

  const address = useMemo<Address | null>(() => {
    if (!ready || !authenticated || !user) return null
    return pickEmbeddedWalletAddress(user.linkedAccounts)
  }, [ready, authenticated, user])

  const walletClient = useMemo<WalletClient | null>(() => {
    if (!address) return null
    if (!BASE_RPC_URL) {
      // RPC URL 未設定は warn のみ、null で返す (呼び出し側で fallback 可能)
      // eslint-disable-next-line no-console
      console.warn(
        '[usePrivyEmbeddedWallet] NEXT_PUBLIC_BASE_RPC_URL is not set — WalletClient will be null',
      )
      return null
    }
    return createWalletClient({
      account: address,
      chain: base,
      transport: http(BASE_RPC_URL),
    })
  }, [address])

  return {
    address,
    walletClient,
    isReady: ready && authenticated && address !== null,
  }
}

export default usePrivyEmbeddedWallet
