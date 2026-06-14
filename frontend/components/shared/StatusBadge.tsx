'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { CheckCircle, AlertTriangle, XCircle, Pause } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'

export interface StatusBadgeProps {
  status: 'NORMAL' | 'SAFE_MODE' | 'HARD_STOP' | 'PAUSED'
}

const statusIconMap = {
  NORMAL: CheckCircle,
  SAFE_MODE: AlertTriangle,
  HARD_STOP: XCircle,
  PAUSED: Pause,
} as const

const statusClassMap = {
  NORMAL: 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
  SAFE_MODE: 'bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800',
  HARD_STOP: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800',
  PAUSED: 'bg-gray-100 dark:bg-gray-800 text-gray-700 border-gray-200 dark:bg-gray-800/50 dark:text-gray-400 dark:border-gray-700',
} as const

export function StatusBadge({ status }: StatusBadgeProps) {
  const t = useTranslations('SharedStatusBadge')
  const Icon = statusIconMap[status]
  const className = statusClassMap[status]

  return (
    <Badge
      variant="outline"
      className={cn('flex items-center gap-1 font-medium', className)}
    >
      <Icon className="h-3 w-3" />
      {t(status)}
    </Badge>
  )
}
