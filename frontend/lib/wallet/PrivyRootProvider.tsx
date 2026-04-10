'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
import { ReactNode } from 'react'

const PrivyRootClient = dynamic(
  () => import('./PrivyRootClient').then(m => m.PrivyRootClient),
  { ssr: false, loading: () => <></> }
)

/**
 * ルートレイアウト用 Privy プロバイダー（SSR無効化済み）。
 * Privy は内部で WagmiProvider を提供するため、既存の wagmi フックはそのまま動作する。
 */
export function PrivyRootProvider({ children }: { children: ReactNode }) {
  return <PrivyRootClient>{children}</PrivyRootClient>
}
