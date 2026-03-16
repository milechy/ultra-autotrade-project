'use client'

import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { PerformanceData } from './types'

interface PerformanceCardProps {
  data: PerformanceData
  className?: string
}

function getWinRateColor(rate: number): string {
  if (rate >= 70) return 'bg-green-500'
  if (rate >= 50) return 'bg-yellow-500'
  return 'bg-red-600'
}

function getWinRateTextColor(rate: number): string {
  if (rate >= 70) return 'text-green-600 dark:text-green-400'
  if (rate >= 50) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}

export function PerformanceCard({ data, className }: PerformanceCardProps) {
  if (!data) return null
  const gainPositive = data.total_gain_jpy >= 0

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">過去実績（{data.period_days}日間）</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Win rate */}
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">
              {data.total_proposals}回提案、{data.positive_results}回でプラス
            </span>
            <span className={cn('text-lg font-bold', getWinRateTextColor(data.win_rate))}>
              {(data.win_rate ?? 0).toFixed(1)}%
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-500', getWinRateColor(data.win_rate))}
              style={{ width: `${data.win_rate}%` }}
            />
          </div>
        </div>

        {/* Total gain */}
        <div className="rounded-lg bg-muted p-4 flex flex-col gap-1">
          <p className="text-sm text-muted-foreground">累計損益</p>
          <p className={cn('text-3xl font-bold', gainPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
            {gainPositive ? '+' : ''}¥{(data.total_gain_jpy ?? 0).toLocaleString('ja-JP')}
          </p>
          <p className="text-sm text-muted-foreground">
            平均 {gainPositive ? '+' : ''}¥{(data.avg_gain_per_trade_jpy ?? 0).toLocaleString('ja-JP')} / 回
          </p>
        </div>

        {/* Disclaimer */}
        <p className="text-xs text-muted-foreground">
          ※ 実績であり保証ではありません。過去の成績は将来の結果を保証しません。
        </p>
      </CardContent>
    </Card>
  )
}
