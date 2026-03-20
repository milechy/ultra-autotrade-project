'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
import { ReactNode } from 'react'

const WalletProviderClient = dynamic(
  () => import('./WalletProviderClient').then(m => m.WalletProviderClient),
  {
    ssr: false,
    loading: () => <></>,
  }
)

export function WalletProvider({ children }: { children: ReactNode }) {
  return <WalletProviderClient>{children}</WalletProviderClient>
}