'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'

const DepositContent = dynamic(
  () => import('./DepositContent').then((m) => ({ default: m.DepositContent })),
  { ssr: false }
)

export default function DepositPage() {
  const t = useTranslations('Deposit')
  return (
    <main className="px-4 py-6 max-w-md mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('pageTitle')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t('pageSubtitle')}
        </p>
      </div>
      <DepositContent />
    </main>
  )
}
