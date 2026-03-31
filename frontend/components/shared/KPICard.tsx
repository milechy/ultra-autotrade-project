'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { TrendingUp, TrendingDown, Minus, LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

export interface KPICardProps {
  label: string
  value: string | number
  prefix?: string
  suffix?: string
  trend?: 'up' | 'down' | 'flat'
  trendValue?: string
  icon?: LucideIcon
}

const trendConfig = {
  up: {
    icon: TrendingUp,
    className: 'text-green-600 dark:text-green-400',
  },
  down: {
    icon: TrendingDown,
    className: 'text-red-600 dark:text-red-400',
  },
  flat: {
    icon: Minus,
    className: 'text-muted-foreground',
  },
} as const

export function KPICard({ label, value, prefix, suffix, trend, trendValue, icon: Icon }: KPICardProps) {
  const TrendIcon = trend ? trendConfig[trend].icon : null

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex flex-col gap-1 flex-1">
            <span className="text-sm text-muted-foreground font-medium">{label}</span>
            <div className="flex items-baseline gap-1">
              {prefix && <span className="text-sm text-muted-foreground">{prefix}</span>}
              <span className="text-2xl font-bold tracking-tight">{value}</span>
              {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
            </div>
            {trend && TrendIcon && (
              <div className={cn('flex items-center gap-1 text-sm', trendConfig[trend].className)}>
                <TrendIcon className="h-4 w-4" />
                {trendValue && <span>{trendValue}</span>}
              </div>
            )}
          </div>
          {Icon && (
            <div className="p-2 rounded-md bg-muted">
              <Icon className="h-5 w-5 text-muted-foreground" />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
