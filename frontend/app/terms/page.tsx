// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import '../arobix/theme.css'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSmartBack } from '@/hooks/useSmartBack'
import { useTranslations } from 'next-intl'

export default function TermsPage() {
  const goBack = useSmartBack()
  const t = useTranslations('Terms')

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
        <p className="text-sm text-zinc-500 mb-8">{t('lastUpdated')}</p>

        <div className="space-y-8 text-sm text-zinc-300 leading-relaxed">
          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section1Title')}</h2>
            <p>{t('section1Body')}</p>
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
            <p>{t('section4Intro')}</p>
            <ul className="mt-2 space-y-2 list-disc list-inside">
              <li>
                <span className="font-medium text-zinc-200">{t('section4Mode2Label')}</span>
                {t('section4Mode2Body')}
              </li>
            </ul>
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
            <p>{t('section9Intro')}</p>
            <ul className="mt-2 space-y-1 list-disc list-inside">
              <li>{t('section9Item1')}</li>
              <li>{t('section9Item2')}</li>
              <li>{t('section9Item3')}</li>
              <li>{t('section9Item4')}</li>
              <li>{t('section9Item5')}</li>
            </ul>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section10Title')}</h2>
            <p>{t('section10Body')}</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">{t('section11Title')}</h2>
            <p>{t('section11Body')}</p>
          </section>

          <div className="pt-4 border-t border-zinc-800 text-xs text-zinc-500 space-y-1">
            <p><span className="text-zinc-400 font-medium">{t('operatorLabel')}: </span>{t('operatorName')}</p>
            <p>{t('operatorLocation')}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
