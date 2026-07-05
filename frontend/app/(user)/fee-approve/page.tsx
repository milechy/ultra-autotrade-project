// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(user)/fee-approve/page.tsx
// URL: /fee-approve
//
// F-S6 non-custodial: 月次手数料の on-chain 徴収を有効にするための
// aToken allowance 承認ページ (PWA / デスクトップ)

import dynamic from 'next/dynamic'
import FeePlanSection from '@/components/user/FeePlanSection'

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
      {/* B-3: 承認前に料率・課金日・「現在は徴収なし」を提示（孤立していた本ページに文脈を付与） */}
      <FeePlanSection />
      <FeeApproveCard />
    </main>
  )
}
