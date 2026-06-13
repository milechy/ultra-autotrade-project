'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ImpactData, PortfolioState } from './types'

interface ImpactCardProps {
  data: ImpactData
  className?: string
}

function formatJpy(amount: number): string {
  return Number(amount ?? 0).toLocaleString('ja-JP')
}

function PortfolioColumn({
  state,
  label,
  highlighted,
}: {
  state: PortfolioState
  label: string
  highlighted?: boolean
}) {
  const t = useTranslations('TransparencyImpactCard')
  if (!state || typeof state !== 'object') return null
  return (
    <div
      className={cn(
        'rounded-lg border p-4 flex flex-col gap-2',
        highlighted ? 'border-primary border-2 bg-primary/5' : 'border-border'
      )}
    >
      <p className={cn('text-sm font-semibold', highlighted && 'text-primary')}>{label}</p>
      <div className="flex flex-col gap-1 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('deposit')}</span>
          <span>${Number(state.deposit_usd ?? 0).toLocaleString()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('borrow')}</span>
          <span>${Number(state.borrow_usd ?? 0).toLocaleString()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('annualRate')}</span>
          <span>{Number(state.net_apy ?? 0).toFixed(2)}%</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('annualYield')}</span>
          <span>¥{formatJpy(state.yield_annual_jpy)}</span>
        </div>
        {state.health_factor !== null && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">{t('healthFactor')}</span>
            <span>{Number(state.health_factor ?? 0).toFixed(2)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function ImpactCard({ data, className }: ImpactCardProps) {
  const t = useTranslations('TransparencyImpactCard')
  if (!data) return null
  const diffPositive = Number(data.diff_yield_annual_jpy ?? 0) >= 0

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          {t('cardTitle', { actionType: data.action_type, amount: Number(data.amount_usd ?? 0).toLocaleString() })}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.before != null && <PortfolioColumn state={data.before} label={t('labelBefore')} />}
          {data.after != null && <PortfolioColumn state={data.after} label={t('labelAfter')} highlighted />}
        </div>

        {/* Diff summary */}
        <div className="rounded-lg bg-muted p-3 flex flex-col gap-1">
          <p className={cn('text-lg font-bold', diffPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400')}>
            {diffPositive ? '+' : ''}¥{formatJpy(data.diff_yield_annual_jpy)} {t('perYear')}
          </p>
          <p className="text-sm text-muted-foreground">{data.metaphor}</p>
        </div>
      </CardContent>
    </Card>
  )
}
