import type { Metadata } from 'next'
import '../styles/globals.css'
import dynamic from 'next/dynamic'

const WalletProvider = dynamic(
  () => import('@/lib/wallet/provider').then(m => m.WalletProvider),
  { ssr: false }
)

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
