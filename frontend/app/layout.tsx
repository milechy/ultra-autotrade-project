import type { Metadata } from 'next'
import '../styles/globals.css'
import { WalletProvider } from '@/lib/wallet/provider'

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
        <WalletProvider>
          {children}
        </WalletProvider>
      </body>
    </html>
  )
}
