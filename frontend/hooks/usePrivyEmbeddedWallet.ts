// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// 2026-05-26 Lane H: Privy 埋込ウォレット (email / SNS ログイン経由で生成) の
// frontend-only ヘルパー。デモ参加者向けに address / chainId / 接続状態を返す。
// 資金は入れない前提 (sign / send は将来 Lane で追加)。

'use client'

import { usePrivy, useWallets } from '@privy-io/react-auth'
import { useMemo } from 'react'

/**
 * Privy が返す chainId は "eip155:84532" または "84532"。
 * 数値に正規化して返す (parse 不能なら null)。
 */
function parsePrivyChainId(chainIdStr: string | undefined): number | null {
  if (!chainIdStr) return null
  const part = chainIdStr.includes(':') ? chainIdStr.split(':')[1] : chainIdStr
  const num = Number.parseInt(part, 10)
  return Number.isNaN(num) ? null : num
}

export type PrivyEmbeddedWalletStatus =
  | 'unconfigured'   // NEXT_PUBLIC_PRIVY_APP_ID 未設定
  | 'initializing'   // Privy SDK 初期化中
  | 'unauthenticated'// 未ログイン
  | 'no-wallet'      // ログイン済みだが embedded wallet 未生成 (createOnLogin 未動作)
  | 'ready'          // 埋込ウォレット利用可能

export interface PrivyEmbeddedWalletState {
  status: PrivyEmbeddedWalletStatus
  /** 0x... 形式の埋込ウォレットアドレス。status === 'ready' のときのみ非 null。 */
  address: `0x${string}` | null
  /** 現在接続中の chainId (数値)。未接続なら null。 */
  chainId: number | null
  /** Privy SDK が ready かつ embedded wallet が存在する。 */
  isReady: boolean
  /** authenticated かどうか (login 状態)。 */
  isAuthenticated: boolean
}

/**
 * usePrivyEmbeddedWallet
 *
 * デモ参加者の埋込ウォレット状態を一箇所で取得するための薄いラッパー。
 * Privy SDK の usePrivy / useWallets の挙動を `status` enum に圧縮し、
 * UI 側の条件分岐を見通し良くする。
 *
 * 既存 (user)/connect/page.tsx と (user)/wallet/* との重複を避けるため、
 * 外部 wallet (MetaMask 等) と embedded wallet の判別は `walletClientType` で行う。
 */
export function usePrivyEmbeddedWallet(): PrivyEmbeddedWalletState {
  const { ready, authenticated } = usePrivy()
  const { wallets, ready: walletsReady } = useWallets()

  return useMemo<PrivyEmbeddedWalletState>(() => {
    const appId =
      typeof process !== 'undefined' ? process.env.NEXT_PUBLIC_PRIVY_APP_ID : ''
    const isConfigured =
      Boolean(appId) && appId !== 'clplaceholder000000000000000000000'

    if (!isConfigured) {
      return {
        status: 'unconfigured',
        address: null,
        chainId: null,
        isReady: false,
        isAuthenticated: false,
      }
    }

    if (!ready || !walletsReady) {
      return {
        status: 'initializing',
        address: null,
        chainId: null,
        isReady: false,
        isAuthenticated: false,
      }
    }

    if (!authenticated) {
      return {
        status: 'unauthenticated',
        address: null,
        chainId: null,
        isReady: false,
        isAuthenticated: false,
      }
    }

    // Privy embedded wallet は walletClientType === 'privy'。
    // 外部 wallet (metamask 等) は別 type なのでここでは除外する。
    const embedded = wallets.find((w) => w.walletClientType === 'privy')
    if (!embedded) {
      return {
        status: 'no-wallet',
        address: null,
        chainId: null,
        isReady: false,
        isAuthenticated: true,
      }
    }

    const addr = embedded.address as `0x${string}`
    return {
      status: 'ready',
      address: addr,
      chainId: parsePrivyChainId(embedded.chainId),
      isReady: true,
      isAuthenticated: true,
    }
  }, [ready, walletsReady, authenticated, wallets])
}
