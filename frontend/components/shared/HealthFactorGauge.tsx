'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'

export interface HealthFactorGaugeProps {
  value: number | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

function getHealthColor(value: number): string {
  if (value >= 2.0) return 'text-green-600'
  if (value >= 1.6) return 'text-yellow-500'
  return 'text-red-600'
}

function getBarWidth(value: number): number {
  // 0-3+ range, cap at 3
  return Math.min((value / 3) * 100, 100)
}

const sizeMap = {
  sm: 'text-xl',
  md: 'text-3xl',
  lg: 'text-5xl',
} as const

export function HealthFactorGauge({ value, size = 'md', className }: HealthFactorGaugeProps) {
  const t = useTranslations('HealthFactor')

  function getHealthLabel(v: number): string {
    if (v >= 2.0) return t('safe')
    if (v >= 1.6) return t('warning')
    return t('danger')
  }

  if (value === null) {
    return (
      <div className={cn('flex flex-col gap-1', className)}>
        <span className="text-sm text-muted-foreground">{t('label')}</span>
        <span className={cn('font-bold text-muted-foreground', sizeMap[size])}>{t('noBorrow')}</span>
      </div>
    )
  }

  const isDanger = value < 1.6

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-muted-foreground">{t('label')}</span>
        <span className={cn('text-xs font-medium', getHealthColor(value))}>
          {getHealthLabel(value)}
        </span>
      </div>
      <span
        className={cn(
          'font-bold',
          sizeMap[size],
          getHealthColor(value),
          isDanger && 'animate-pulse'
        )}
      >
        {value.toFixed(2)}
      </span>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            value >= 2.0
              ? 'bg-green-500'
              : value >= 1.6
              ? 'bg-yellow-500'
              : 'bg-red-600'
          )}
          style={{ width: `${getBarWidth(value)}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>0</span>
        <span className="text-red-500">{t('limit')}</span>
        <span>3+</span>
      </div>
    </div>
  )
}
