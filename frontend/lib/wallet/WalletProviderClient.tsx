'use client'

import { ReactNode, useState, useEffect } from 'react'
import { WagmiProvider } from 'wagmi'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createWeb3Modal } from '@web3modal/wagmi/react'
import { wagmiConfig, projectId } from './config'

let web3ModalInitialized = false

export function WalletProviderClient({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient())

  useEffect(() => {
    if (!web3ModalInitialized) {
      createWeb3Modal({
        wagmiConfig,
        projectId,
      })
      web3ModalInitialized = true
    }
  }, [])

  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    </WagmiProvider>
  )
}
