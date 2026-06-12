'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { AiTransparencyCard } from '@/components/transparency/AiTransparencyCard'

export function LatestDecision() {
  const t = useTranslations('Dashboard')
  return (
    <div className="space-y-2">
      <AiTransparencyCard />
      <div className="flex justify-end">
        <Link href="/user/decisions" className="text-xs text-blue-400 hover:text-blue-300">
          {t('viewDecisionHistory')}
        </Link>
      </div>
    </div>
  )
}
