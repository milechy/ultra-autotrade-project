// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback, useEffect, useState } from 'react'
import { getAuthToken } from '@/lib/auth/token-key'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

// 取得状態。
//  - idle    : enabled=false（fetch していない）
//  - loading : API 取得中
//  - ready   : wallet_address 取得済み
//  - empty   : 認証済みだが記録上のアドレス無し / 未認証
//  - error   : 取得失敗（refetch 可能）
export type LinkedAddressState = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

export interface LinkedWalletAddress {
  address: string | null
  /** Smart Wallet (ERC-4337) アドレス。未設定 (EOA ユーザー) なら null。 */
  smartWalletAddress: string | null
  state: LinkedAddressState
  refetch: () => void
}

/**
 * useLinkedWalletAddress
 *
 * バックエンドに記録された連携ウォレットアドレス（`/api/user/settings` の
 * `wallet_address`）を取得する「表示専用」hook。live wallet（injected / Privy
 * embedded）が取れないときのフォールバック表示に使う。
 *
 * 返すのはアドレス文字列のみで、署名 provider/signer は持たない（記録上の値のため）。
 * 署名が必要な経路は live wallet（useWallet の signer）を使うこと。
 *
 * @param enabled false の間は fetch せず idle を返す。live wallet がある場合に
 *   無駄な API 呼び出しを避けるためのスイッチ。
 *
 * token key は `@/lib/auth/token-key` の getAuthToken に統一（旧 'ultra_auth_token'
 * 直読みは key 不整合により永久ローディングを引き起こすため使わない）。
 */
export function useLinkedWalletAddress(enabled = true): LinkedWalletAddress {
  const [address, setAddress] = useState<string | null>(null)
  const [smartWalletAddress, setSmartWalletAddress] = useState<string | null>(null)
  const [state, setState] = useState<LinkedAddressState>('idle')

  const fetchAddress = useCallback(async () => {
    if (!enabled) {
      setState('idle')
      return
    }

    const token = getAuthToken()
    if (!token) {
      // 認証トークンが無い = 記録も引けない（空状態）
      setAddress(null)
      setSmartWalletAddress(null)
      setState('empty')
      return
    }

    setState('loading')
    try {
      const res = await fetch(`${API_BASE}/api/user/settings`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        // 非2xx は fail-visible（永久ローディングにしない）
        setState('error')
        return
      }
      const data = (await res.json()) as {
        wallet_address?: string | null
        smart_wallet_address?: string | null
      } | null
      setSmartWalletAddress(data?.smart_wallet_address ?? null)
      if (data?.wallet_address) {
        setAddress(data.wallet_address)
        setState('ready')
      } else {
        setAddress(null)
        setState(data?.smart_wallet_address ? 'ready' : 'empty')
      }
    } catch {
      // ネットワーク失敗等は fail-visible（refetch 可能）
      setState('error')
    }
  }, [enabled])

  useEffect(() => {
    void fetchAddress()
  }, [fetchAddress])

  return { address, smartWalletAddress, state, refetch: fetchAddress }
}
