'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-fee-approve/page.tsx
// URL: /liff-fee-approve
//
// F-S6 non-custodial: LIFF 内からアクセスする手数料 allowance 承認ページ

import { useTranslations } from 'next-intl'
import { useLiff } from '@/hooks/useLiff'
import { FeeApproveCard } from '@/components/user/FeeApproveCard'
import { StripePaymentMethodCard } from '@/components/user/StripePaymentMethodCard'
import FeePlanSection from '@/components/user/FeePlanSection'
import { isFeeCollectionEnabled } from '@/lib/flags'
import { BrowserLoginPrompt } from '../_components/BrowserLoginPrompt'

export default function LiffFeeApprovePage() {
  const t = useTranslations('LiffFeeApprove')
  const { isReady, error, liffConfigured } = useLiff()

  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <p className="text-zinc-400 text-sm">{t('loading')}</p>
      </div>
    )
  }

  // error 画面は LIFF モードの実 init 失敗時のみ。ブラウザ degrade では error は立たない。
  if (liffConfigured && error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-red-400 text-sm text-center">
          {t('liffInitError', { error })}
        </p>
      </div>
    )
  }

  // 黒画面の if(!isLoggedIn) ガードは (liff)/layout.tsx の中央集権 degrade ガードへ移譲済み。
  const token =
    typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null

  if (!token) {
    // LIFF モード: LINE idToken から JWT を発行するため liff-login へ。
    if (liffConfigured) {
      if (typeof window !== 'undefined') {
        window.location.replace('/liff-login')
      }
      return (
        <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
          <p className="text-zinc-400 text-sm">{t('reauthing')}</p>
        </div>
      )
    }
    // ブラウザ degrade モード: Privy wallet 署名で JWT を取得する。
    return <BrowserLoginPrompt />
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold">{t('title')}</h1>
        <p className="text-sm text-zinc-400 mt-1">
          {t('description')}
        </p>
      </div>
      {/* B-3: 承認前に料率・課金日・「現在は徴収なし」を提示 */}
      <div className="mb-4">
        <FeePlanSection />
      </div>
      {/* 月額徴収撤廃（2026-07-09・当面無料）により、カード登録(Stripe)+on-chain allowance 承認の
          徴収UIは既定で非表示。徴収を再開する場合のみ isFeeCollectionEnabled で表示する。 */}
      {isFeeCollectionEnabled() && (
        <>
          {/* F-7: サブスク月額分はクレカ(Stripe)で回収。成功報酬+yield超過分はon-chainで回収(下記)。 */}
          <div className="mb-4">
            <StripePaymentMethodCard />
          </div>
          <FeeApproveCard />
        </>
      )}
    </div>
  )
}
