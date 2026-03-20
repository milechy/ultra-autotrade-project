// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type StatusType = 'NORMAL' | 'SAFE_MODE' | 'HARD_STOP' | string

const statusConfig: Record<string, { label: string; className: string }> = {
  NORMAL: { label: 'NORMAL', className: 'bg-green-100 text-green-800 border-green-200' },
  SAFE_MODE: { label: 'SAFE MODE', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
  HARD_STOP: { label: 'HARD STOP', className: 'bg-red-100 text-red-800 border-red-200' },
}

export function StatusBadge({ status }: { status: StatusType }) {
  const config = statusConfig[status] ?? { label: status, className: 'bg-gray-100 text-gray-700 border-gray-200' }
  return (
    <Badge variant="outline" className={cn('font-mono text-xs font-bold', config.className)}>
      {config.label}
    </Badge>
  )
}
