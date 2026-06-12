'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { HelpCircle } from 'lucide-react'
import { useTranslations } from 'next-intl'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'

const FAQ_ITEMS = [
  'item1',
  'item2',
  'item3',
  'item4',
  'item5',
  'item6',
  'item7',
  'item8',
  'item9',
  'item10',
] as const

export default function HelpPage() {
  const t = useTranslations('Help')

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center gap-3 mb-2">
          <HelpCircle className="h-6 w-6 text-blue-400" />
          <h1 className="text-2xl font-bold">{t('pageTitle')}</h1>
        </div>
        <p className="text-sm text-zinc-500 mb-8">{t('pageSubtitle')}</p>

        <Accordion type="single" collapsible className="space-y-0">
          {FAQ_ITEMS.map((item) => (
            <AccordionItem
              key={item}
              value={item}
              className="border-zinc-800"
            >
              <AccordionTrigger className="text-zinc-100 hover:text-zinc-100 hover:no-underline text-sm font-medium">
                {t(`faqs.${item}Question`)}
              </AccordionTrigger>
              <AccordionContent className="text-zinc-400 text-sm leading-relaxed">
                {t(`faqs.${item}Answer`)}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </div>
  )
}
