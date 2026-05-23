'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { PrivyProvider } from '@privy-io/react-auth'
import { base, baseSepolia } from 'wagmi/chains'
import { WagmiProvider } from 'wagmi'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactNode, useState } from 'react'
import { wagmiConfig } from './config'

/**
 * P1 (privy-embedded-wallet-mvp):
 * - LINE / Email を一次 login method として明示
 *   (既存の 'wallet' は外部 wallet 連携用に維持)
 * - 全 user に embedded wallet を自動作成 (createOnLogin: 'all-users')
 *
 * `loginMethods` は他 PR (E2E test fixture や Slack login button 等) から
 * 再利用できるよう const + as const + export として公開する。
 */
export const loginMethods = ['line', 'email', 'wallet'] as const
export type PrivyLoginMethod = (typeof loginMethods)[number]

const PLACEHOLDER_APP_ID = 'clplaceholder000000000000000000000'

const appId = process.env.NEXT_PUBLIC_PRIVY_APP_ID || ''

// Skip PrivyProvider when App ID is absent — JWT auth remains fully functional.
// 環境変数未設定/placeholder の状態でも console に「なぜ Privy が無効か」を出す。
const isPrivyConfigured = appId && appId !== PLACEHOLDER_APP_ID

if (typeof window !== 'undefined' && !isPrivyConfigured) {
  // eslint-disable-next-line no-console
  console.warn(
    '[PrivyRootClient] NEXT_PUBLIC_PRIVY_APP_ID is not set or is a placeholder — ' +
      'Privy embedded wallet flow is disabled. ' +
      'JWT-based login (/auth/login, /auth/wallet/connect) continues to work. ' +
      'Set NEXT_PUBLIC_PRIVY_APP_ID at build time (Docker build.args) to enable.',
  )
}

// 2026-05-01: defaultChain を hardcode (baseSepolia) から env 駆動に変更 (mainnet 切替)
// NEXT_PUBLIC_DEFAULT_CHAIN_ID は build-time に Docker build.args から焼き込まれる
const defaultChainId = parseInt(process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453')
// `base` を主軸 default に据える。env で 84532 を明示した場合のみ baseSepolia を採用する。
// (viem chain object をそのまま `defaultChain` に渡す Privy 仕様に準拠)
export const defaultChain = defaultChainId === 84532 ? baseSepolia : base

export function PrivyRootClient({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient())
  if (!isPrivyConfigured) {
    return (
      <WagmiProvider config={wagmiConfig}>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </WagmiProvider>
    )
  }
  return (
    <PrivyProvider
      appId={appId}
      config={{
        loginMethods: [...loginMethods],
        appearance: {
          theme: 'dark',
          accentColor: '#6366f1',
        },
        supportedChains: [base, baseSepolia],
        defaultChain,
        embeddedWallets: {
          ethereum: { createOnLogin: 'all-users' },
        },
      }}
    >
      <WagmiProvider config={wagmiConfig}>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </WagmiProvider>
    </PrivyProvider>
  )
}
