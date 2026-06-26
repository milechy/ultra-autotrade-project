// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import '../arobix/theme.css'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSmartBack } from '@/hooks/useSmartBack'
import { useTranslations } from 'next-intl'

export default function TokushohoPage() {
  const goBack = useSmartBack()
  const t = useTranslations('Tokushoho')

  // 特定商取引法に基づく表示の項目（ラベル / 値）。順序は表示順。
  const rows: { label: string; value: string }[] = [
    { label: t('providerLabel'), value: t('providerName') },
    { label: t('jpOperatorLabel'), value: t('jpOperatorName') },
    { label: t('managerLabel'), value: t('managerName') },
    { label: t('addressLabel'), value: t('addressValue') },
    { label: t('phoneLabel'), value: t('phoneValue') },
    { label: t('hoursLabel'), value: t('hoursValue') },
    { label: t('emailLabel'), value: t('emailValue') },
    { label: t('priceLabel'), value: t('priceValue') },
    { label: t('extraCostLabel'), value: t('extraCostValue') },
    { label: t('paymentMethodLabel'), value: t('paymentMethodValue') },
    { label: t('deliveryLabel'), value: t('deliveryValue') },
    { label: t('cancelLabel'), value: t('cancelValue') },
    { label: t('envLabel'), value: t('envValue') },
  ]

  return (
    <div className="arobix-root min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <Button
          variant="ghost"
          size="sm"
          className="mb-6 text-zinc-400 hover:text-zinc-100"
          onClick={goBack}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('back')}
        </Button>

        <h1 className="text-2xl font-bold mb-2">{t('title')}</h1>
        <p className="text-sm text-zinc-500 mb-6">{t('lastUpdated')}</p>
        <p className="text-sm text-zinc-400 mb-8 leading-relaxed">{t('intro')}</p>

        <dl className="divide-y divide-zinc-800 border-t border-zinc-800">
          {rows.map((row) => (
            <div key={row.label} className="py-4 sm:grid sm:grid-cols-3 sm:gap-4">
              <dt className="text-sm font-medium text-zinc-200">{row.label}</dt>
              <dd className="mt-1 text-sm text-zinc-400 leading-relaxed sm:col-span-2 sm:mt-0 whitespace-pre-line">
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
