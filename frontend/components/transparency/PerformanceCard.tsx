'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { PerformanceData } from './types'

interface PerformanceCardProps {
  data: PerformanceData
  className?: string
}

function getWinRateColor(rate: number | string): string {
  const n = Number(rate ?? 0)
  if (n >= 70) return 'bg-green-500'
  if (n >= 50) return 'bg-yellow-500'
  return 'bg-red-600'
}

function getWinRateTextColor(rate: number | string): string {
  const n = Number(rate ?? 0)
  if (n >= 70) return 'text-green-600 dark:text-green-400'
  if (n >= 50) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}

export function PerformanceCard({ data, className }: PerformanceCardProps) {
  const t = useTranslations('TransparencyPerformanceCard')
  if (!data) return null
  const gainPositive = Number(data.total_gain_jpy ?? 0) >= 0

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{t('title', { days: data.period_days })}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Win rate */}
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">
              {t('proposalSummary', { total: data.total_proposals, positive: data.positive_results })}
            </span>
            <span className={cn('text-lg font-bold', getWinRateTextColor(data.win_rate))}>
              {Number(data.win_rate ?? 0).toFixed(1)}%
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-500', getWinRateColor(data.win_rate))}
              style={{ width: `${Number(data.win_rate ?? 0)}%` }}
            />
          </div>
        </div>

        {/* Total gain */}
        <div className="rounded-lg bg-muted p-4 flex flex-col gap-1">
          <p className="text-sm text-muted-foreground">{t('totalGain')}</p>
          <p className={cn('text-3xl font-bold', gainPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
            {gainPositive ? '+' : ''}¥{Number(data.total_gain_jpy ?? 0).toLocaleString('ja-JP')}
          </p>
          <p className="text-sm text-muted-foreground">
            {t('avgPerTrade', { sign: gainPositive ? '+' : '', amount: Number(data.avg_gain_per_trade_jpy ?? 0).toLocaleString('ja-JP') })}
          </p>
        </div>

        {/* Disclaimer */}
        <p className="text-xs text-muted-foreground">
          {t('disclaimer')}
        </p>
      </CardContent>
    </Card>
  )
}
