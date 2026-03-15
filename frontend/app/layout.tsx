import type { Metadata } from 'next'
import '../styles/globals.css'
import { WagmiRootProvider } from '@/lib/wallet/WagmiRootProvider'

export const metadata: Metadata = {
  title: 'Ultra AutoTrade',
  description: 'Automated trading dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <body>
        <WagmiRootProvider>
          {children}
        </WagmiRootProvider>
      </body>
    </html>
  )
}
