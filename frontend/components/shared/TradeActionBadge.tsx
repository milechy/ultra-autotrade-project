'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export interface TradeActionBadgeProps {
  action: 'BUY' | 'SELL' | 'HOLD'
}

const actionConfig = {
  BUY: {
    labelKey: 'labelBuy' as const,
    icon: TrendingUp,
    className: 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
  },
  SELL: {
    labelKey: 'labelSell' as const,
    icon: TrendingDown,
    className: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800',
  },
  HOLD: {
    labelKey: 'labelHold' as const,
    icon: Minus,
    className: 'bg-gray-100 dark:bg-gray-800 text-gray-700 border-gray-200 dark:bg-gray-800/50 dark:text-gray-400 dark:border-gray-700',
  },
} as const

export function TradeActionBadge({ action }: TradeActionBadgeProps) {
  const t = useTranslations('SharedTradeActionBadge')
  const config = actionConfig[action]
  const Icon = config.icon

  return (
    <Badge
      variant="outline"
      className={cn('flex items-center gap-1 font-semibold', config.className)}
    >
      <Icon className="h-3 w-3" />
      {t(config.labelKey)}
    </Badge>
  )
}
