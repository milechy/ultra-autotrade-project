'use client'

import dynamic from 'next/dynamic'
import { ReactNode } from 'react'

const WagmiRootClient = dynamic(
  () => import('./WagmiRootClient').then(m => m.WagmiRootClient),
  { ssr: false, loading: () => <></> }
)

/**
 * ルートレイアウト用 Wagmi プロバイダー（SSR無効化済み）。
 * web3modal は初期化しないため、全ページで安全に使用できる。
 */
export function WagmiRootProvider({ children }: { children: ReactNode }) {
  return <WagmiRootClient>{children}</WagmiRootClient>
}
