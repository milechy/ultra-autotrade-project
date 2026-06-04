// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(user)/fee-approve/page.tsx
// URL: /fee-approve
//
// F-S6 non-custodial: 月次手数料の on-chain 徴収を有効にするための
// aToken allowance 承認ページ (PWA / デスクトップ)

import dynamic from 'next/dynamic'

const FeeApproveCard = dynamic(
  () => import('@/components/user/FeeApproveCard').then((m) => ({ default: m.FeeApproveCard })),
  { ssr: false }
)

export default function FeeApprovePage() {
  return (
    <main className="px-4 py-6 max-w-md mx-auto space-y-4">
      <div>
        <h1 className="text-2xl font-bold">手数料承認</h1>
        <p className="text-sm text-muted-foreground mt-1">
          月次手数料の自動徴収を有効にするための承認を行います
        </p>
      </div>
      <FeeApproveCard />
    </main>
  )
}
