// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import dynamic from 'next/dynamic'

const DepositContent = dynamic(
  () => import('./DepositContent').then((m) => ({ default: m.DepositContent })),
  { ssr: false }
)

export default function DepositPage() {
  return (
    <main className="px-4 py-6 max-w-md mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">入金</h1>
        <p className="text-sm text-muted-foreground mt-1">
          USDCをあなたのウォレットに直接入金してください
        </p>
      </div>
      <DepositContent />
    </main>
  )
}
