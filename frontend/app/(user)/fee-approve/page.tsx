// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(user)/fee-approve/page.tsx
// URL: /fee-approve
//
// F-S6 non-custodial: 月次手数料の on-chain 徴収を有効にするための
// aToken allowance 承認ページ (PWA / デスクトップ)

import dynamic from 'next/dynamic'
import FeePlanSection from '@/components/user/FeePlanSection'
import { isFeeCollectionEnabled } from '@/lib/flags'

const FeeApproveCard = dynamic(
  () => import('@/components/user/FeeApproveCard').then((m) => ({ default: m.FeeApproveCard })),
  { ssr: false }
)

const StripePaymentMethodCard = dynamic(
  () =>
    import('@/components/user/StripePaymentMethodCard').then((m) => ({
      default: m.StripePaymentMethodCard,
    })),
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
      {/* 月額徴収撤廃（2026-07-09・当面無料）により、カード登録(Stripe)+on-chain allowance 承認の
          徴収UIは既定で非表示。徴収を再開する場合のみ isFeeCollectionEnabled で表示する。 */}
      {isFeeCollectionEnabled() && (
        <>
          {/* F-7: サブスク月額分はクレカ(Stripe)で回収。成功報酬+yield超過分はon-chainで回収(下記)。 */}
          <StripePaymentMethodCard />
          <FeeApproveCard />
        </>
      )}
    </main>
  )
}
