'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { PrivyProvider } from '@privy-io/react-auth'
import { base, baseSepolia } from 'wagmi/chains'
import { WagmiProvider } from 'wagmi'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactNode, useState } from 'react'
import { wagmiConfig } from './config'

const appId = process.env.NEXT_PUBLIC_PRIVY_APP_ID || ''

// Skip PrivyProvider when App ID is absent — JWT auth remains fully functional.
const isPrivyConfigured = appId && appId !== 'clplaceholder000000000000000000000'

// 2026-05-01: defaultChain を hardcode (baseSepolia) から env 駆動に変更 (mainnet 切替)
// NEXT_PUBLIC_DEFAULT_CHAIN_ID は build-time に Docker build.args から焼き込まれる
const defaultChainId = parseInt(process.env.NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453')
const defaultChain = defaultChainId === 8453 ? base : baseSepolia

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
        // 2026-05-26 Lane H: SNS (google/apple) を loginMethods に追加し、デモ参加者が
        // 外部 wallet 不要で onboarding できるようにする。LINE は OAuth 設定別途必要 (別 Lane)。
        loginMethods: ['email', 'google', 'apple', 'wallet'],
        appearance: {
          theme: 'dark',
          accentColor: '#6366f1',
        },
        supportedChains: [base, baseSepolia],
        defaultChain,
        embeddedWallets: {
          // 'all-users' = 既存 wallet 有無に関わらず全ユーザーに埋込ウォレット作成。
          // メール/SNS ログイン経路では必須 (資金は入れない demo 前提)。
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
