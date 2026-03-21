// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { Activity, TrendingUp, Receipt } from 'lucide-react'
import { KPICard } from '@/components/shared'

export interface StatsCardsProps {
  totalCount: number
  totalProfitUSD: number
  totalFeeUSD: number
}

export function StatsCards({ totalCount, totalProfitUSD, totalFeeUSD }: StatsCardsProps) {
  const profitFormatted =
    totalProfitUSD >= 0
      ? `+$${totalProfitUSD.toFixed(2)}`
      : `-$${Math.abs(totalProfitUSD).toFixed(2)}`

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      <KPICard
        label="総取引数"
        value={`${totalCount}件`}
        icon={Activity}
      />
      <KPICard
        label="総利益"
        value={profitFormatted}
        trend={totalProfitUSD >= 0 ? 'up' : 'down'}
        icon={TrendingUp}
      />
      <KPICard
        label="総手数料"
        value={`$${totalFeeUSD.toFixed(2)}`}
        icon={Receipt}
      />
    </div>
  )
}
