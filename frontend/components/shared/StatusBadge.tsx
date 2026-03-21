'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { CheckCircle, AlertTriangle, XCircle, Pause } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export interface StatusBadgeProps {
  status: 'NORMAL' | 'SAFE_MODE' | 'HARD_STOP' | 'PAUSED'
}

const statusConfig = {
  NORMAL: {
    label: '正常',
    icon: CheckCircle,
    className: 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
  },
  SAFE_MODE: {
    label: 'セーフモード',
    icon: AlertTriangle,
    className: 'bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800',
  },
  HARD_STOP: {
    label: '緊急停止',
    icon: XCircle,
    className: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800',
  },
  PAUSED: {
    label: '一時停止',
    icon: Pause,
    className: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-800/50 dark:text-gray-400 dark:border-gray-700',
  },
} as const

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status]
  const Icon = config.icon

  return (
    <Badge
      variant="outline"
      className={cn('flex items-center gap-1 font-medium', config.className)}
    >
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  )
}
