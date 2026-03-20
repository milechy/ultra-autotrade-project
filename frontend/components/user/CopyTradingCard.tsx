'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import { TrendingUp, Users, ShieldCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { StrategyWithPerformance } from '@/lib/api/copy_trading'

type Props = {
  strategy: StrategyWithPerformance
  isSubscribed: boolean
  onSubscribe: (strategy: StrategyWithPerformance) => void
  onUnsubscribe: (strategyId: string) => void
}

const RISK_COLORS = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-red-100 text-red-800',
} as const

export function CopyTradingCard({ strategy, isSubscribed, onSubscribe, onUnsubscribe }: Props) {
  const t = useTranslations('CopyTrading')
  const p = strategy.performance

  const riskLabel = {
    low: t('riskLow'),
    medium: t('riskMedium'),
    high: t('riskHigh'),
  }[strategy.risk_level]

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base truncate">{strategy.name}</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
              {strategy.description}
            </p>
          </div>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${RISK_COLORS[strategy.risk_level]}`}
          >
            {riskLabel}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {p && (
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">{t('winRate')}</span>
              <span className="font-semibold">{(p.win_rate * 100).toFixed(1)}%</span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">{t('sharpeRatio')}</span>
              <span className="font-semibold">{p.sharpe_ratio.toFixed(2)}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">{t('totalPnl')}</span>
              <span className={`font-semibold ${parseFloat(p.total_pnl) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {parseFloat(p.total_pnl) >= 0 ? '+' : ''}{parseFloat(p.total_pnl).toFixed(2)} USDT
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">{t('trades')}</span>
              <span className="font-semibold">{p.total_trades}</span>
            </div>
          </div>
        )}
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Users className="h-3 w-3" />
            <span>{t('strategist')}: {strategy.strategist_id.slice(0, 8)}...</span>
          </div>
          {isSubscribed ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onUnsubscribe(strategy.id)}
              className="text-xs"
            >
              {t('unsubscribe')}
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => onSubscribe(strategy)}
              className="text-xs"
            >
              {t('subscribe')}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}