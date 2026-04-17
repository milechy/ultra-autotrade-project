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

export function PrivyRootClient({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient())
  if (!isPrivyConfigured) {
    return (
      <QueryClientProvider client={queryClient}>
        <WagmiProvider config={wagmiConfig}>
          {children}
        </WagmiProvider>
      </QueryClientProvider>
    )
  }
  return (
    <PrivyProvider
      appId={appId}
      config={{
        loginMethods: ['email', 'wallet'],
        appearance: {
          theme: 'dark',
          accentColor: '#6366f1',
        },
        supportedChains: [baseSepolia, base],
        defaultChain: baseSepolia,
        embeddedWallets: {
          ethereum: { createOnLogin: 'users-without-wallets' },
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    </PrivyProvider>
  )
}
