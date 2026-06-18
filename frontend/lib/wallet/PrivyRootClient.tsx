'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { PrivyProvider } from '@privy-io/react-auth'
import { SmartWalletsProvider } from '@privy-io/react-auth/smart-wallets'
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
          // Arobix ブランド統一: アプリの primary CTA（紫系グラデ）に合わせ、
          // Privy モーダルの accentColor を Arobix purple に揃える。
          theme: 'dark',
          accentColor: '#6e56cf',
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
      {/* SmartWalletsProvider: Privy Smart Wallet (ERC-4337 AA) を有効化する (slice4a)。
          bundler/paymaster は Privy ダッシュボード設定 (track C) から供給される。
          useSmartWallets() が SCW client を返し、slice4c で署名経路が UserOp 送信に使う。
          非カストディアル不変条件: SCW の owner はユーザー embedded EOA のみ (§1.5)。 */}
      <SmartWalletsProvider>
        <WagmiProvider config={wagmiConfig}>
          <QueryClientProvider client={queryClient}>
            {children}
          </QueryClientProvider>
        </WagmiProvider>
      </SmartWalletsProvider>
    </PrivyProvider>
  )
}
