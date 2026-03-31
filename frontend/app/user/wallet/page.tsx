// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import dynamic from 'next/dynamic'

const WalletContent = dynamic(
  () => import('./WalletContent').then((m) => ({ default: m.WalletContent })),
  { ssr: false }
)

export default function WalletPage() {
  return (
    <main className="px-4 py-6 max-w-md mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">ウォレット接続</h1>
        <p className="text-sm text-muted-foreground mt-1">
          テストネットに接続してください
        </p>
      </div>
      <WalletContent />
    </main>
  )
}
