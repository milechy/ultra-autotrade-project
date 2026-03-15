'use client'

import { ReactNode, useState, useEffect } from 'react'
import { WagmiProvider } from 'wagmi'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createWeb3Modal } from '@web3modal/wagmi/react'
import { wagmiConfig, projectId } from './config'
import { WalletErrorBoundary } from './WalletErrorBoundary'

let web3ModalInitialized = false

export function WalletProviderClient({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient())

  useEffect(() => {
    if (!web3ModalInitialized) {
      try {
        createWeb3Modal({
          wagmiConfig,
          projectId,
          themeMode: 'dark',
          themeVariables: {
            '--w3m-color-mix': '#000000',
            '--w3m-color-mix-strength': 40,
          },
        })
        web3ModalInitialized = true
      } catch (e) {
        console.warn('[WalletProvider] createWeb3Modal failed (non-fatal):', e)
      }
    }
  }, [])

  return (
    <WalletErrorBoundary>
      <WagmiProvider config={wagmiConfig}>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </WagmiProvider>
    </WalletErrorBoundary>
  )
}
