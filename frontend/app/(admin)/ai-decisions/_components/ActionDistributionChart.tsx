'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import type { AiDecision } from '../mock-data'
import type { PieEntry } from './ActionDistributionChartRecharts'

// recharts は SSR でクラッシュするため dynamic import + ssr: false が必須
const ActionDistributionChartRecharts = dynamic(
  () =>
    import('./ActionDistributionChartRecharts').then(
      (m) => m.ActionDistributionChartRecharts
    ),
  { ssr: false }
)

interface ActionDistributionChartProps {
  decisions: AiDecision[]
}

export function ActionDistributionChart({ decisions }: ActionDistributionChartProps) {
  const t = useTranslations('AdminActionDistributionChart')
  const buyCount = decisions.filter((d) => d.final_action === 'BUY').length
  const sellCount = decisions.filter((d) => d.final_action === 'SELL').length
  const holdCount = decisions.filter((d) => d.final_action === 'HOLD').length

  const pieData: PieEntry[] = [
    { name: 'BUY', value: buyCount },
    { name: 'SELL', value: sellCount },
    { name: 'HOLD', value: holdCount },
  ].filter((d) => d.value > 0)

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
        {t('title')}
      </h3>
      {pieData.length > 0 ? (
        <ActionDistributionChartRecharts pieData={pieData} />
      ) : (
        <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
          {t('noData')}
        </div>
      )}
    </div>
  )
}
