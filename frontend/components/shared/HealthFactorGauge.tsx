'use client'

import { cn } from '@/lib/utils'

interface HealthFactorGaugeProps {
  value: number | null
  className?: string
}

function getHealthColor(value: number): string {
  if (value >= 2.0) return 'text-green-600'
  if (value >= 1.6) return 'text-yellow-500'
  return 'text-red-600'
}

function getHealthLabel(value: number): string {
  if (value >= 2.0) return 'Safe'
  if (value >= 1.6) return 'Caution'
  return 'DANGER'
}

function getBarWidth(value: number): number {
  // 0-3+ range, cap at 3
  return Math.min((value / 3) * 100, 100)
}

export function HealthFactorGauge({ value, className }: HealthFactorGaugeProps) {
  if (value === null) {
    return (
      <div className={cn('flex flex-col gap-1', className)}>
        <span className="text-sm text-muted-foreground">Health Factor</span>
        <span className="text-2xl font-bold text-muted-foreground">--</span>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-muted-foreground">Health Factor</span>
        <span className={cn('text-xs font-medium', getHealthColor(value))}>
          {getHealthLabel(value)}
        </span>
      </div>
      <span className={cn('text-3xl font-bold', getHealthColor(value))}>
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
        <span className="text-red-500">1.6 limit</span>
        <span>3+</span>
      </div>
    </div>
  )
}
