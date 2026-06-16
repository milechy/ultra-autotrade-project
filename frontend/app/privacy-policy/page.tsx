// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import '../arobix/theme.css'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSmartBack } from '@/hooks/useSmartBack'
import { useTranslations } from 'next-intl'

export default function PrivacyPolicyPage() {
  const goBack = useSmartBack()
  const t = useTranslations('PrivacyPolicy')

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

        <h1 className="text-2xl font-bold mb-2">{t('pageTitle')}</h1>
        <p className="text-sm text-zinc-500 mb-8">{t('lastUpdated')}</p>

        <div className="space-y-8 text-sm text-zinc-300 leading-relaxed">
          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section1Title')}</h2>
            <p>{t('section1Intro')}</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>{t('section1Item1')}</li>
              <li>{t('section1Item2')}</li>
              <li>{t('section1Item3')}</li>
              <li>{t('section1Item4')}</li>
            </ul>
            <p className="mt-2 text-xs text-zinc-500">{t('section1Note')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section2Title')}</h2>
            <p>{t('section2Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section3Title')}</h2>
            <p>{t('section3Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section4Title')}</h2>
            <p>{t('section4Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section5Title')}</h2>
            <p>{t('section5Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section6Title')}</h2>
            <p>{t('section6Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section7Title')}</h2>
            <p>{t('section7Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section8Title')}</h2>
            <p>{t('section8Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section9Title')}</h2>
            <p>{t('section9Body')}</p>
          </section>
        </div>
      </div>
    </div>
  )
}
