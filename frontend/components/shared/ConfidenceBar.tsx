'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { cn } from '@/lib/utils'

export interface ConfidenceBarProps {
  value: number
  threshold?: number
  showLabel?: boolean
}

export function ConfidenceBar({ value, threshold = 70, showLabel = true }: ConfidenceBarProps) {
  const clamped = Math.min(100, Math.max(0, value))
  const isAboveThreshold = clamped >= threshold

  return (
    <div className="flex flex-col gap-1 w-full">
      {showLabel && (
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">信頼度</span>
          <span className={cn('font-medium', isAboveThreshold ? 'text-green-600 dark:text-green-400' : 'text-blue-600 dark:text-blue-400')}>
            {clamped}%
          </span>
        </div>
      )}
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            isAboveThreshold
              ? 'bg-green-500 dark:bg-green-600'
              : 'bg-blue-400 dark:bg-blue-500'
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {threshold && (
        <div className="flex justify-end text-xs text-muted-foreground">
          <span>閾値: {threshold}%</span>
        </div>
      )}
    </div>
  )
}
