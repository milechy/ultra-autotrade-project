'use client'

import { ReactNode } from 'react'
import { WagmiProvider } from 'wagmi'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createWeb3Modal } from '@web3modal/wagmi/react'
import { wagmiConfig, projectId } from './config'
import { useState, useEffect } from 'react'

let web3ModalInitialized = false

export function WalletProvider({ children }: { children: ReactNode }) {
  if (typeof window === 'undefined') {
    return <>{children}</>
  }

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
