// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { Button } from '@/components/ui/button'
import { DateRangeFilter } from '@/components/shared'
import { cn } from '@/lib/utils'

export type OperationType = 'ALL' | 'SUPPLY' | 'WITHDRAW' | 'BORROW' | 'REPAY'

export interface TransactionFiltersProps {
  activeType: OperationType
  onTypeChange: (type: OperationType) => void
  onDateRangeChange: (range: { from: Date; to: Date } | 'all') => void
}

const OPERATION_TYPES: OperationType[] = ['ALL', 'SUPPLY', 'WITHDRAW', 'BORROW', 'REPAY']

const OPERATION_LABELS: Record<OperationType, string> = {
  ALL: '全て',
  SUPPLY: '供給',
  WITHDRAW: '引き出し',
  BORROW: '借入',
  REPAY: '返済',
}

export function TransactionFilters({
  activeType,
  onTypeChange,
  onDateRangeChange,
}: TransactionFiltersProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:flex-wrap">
      {/* Operation type filter */}
      <div className="flex items-center gap-1 flex-wrap">
        {OPERATION_TYPES.map((type) => (
          <Button
            key={type}
            variant={activeType === type ? 'default' : 'outline'}
            size="sm"
            onClick={() => onTypeChange(type)}
            className={cn(
              'h-8 px-3 text-xs',
              activeType === type && 'font-semibold'
            )}
          >
            {OPERATION_LABELS[type]}
          </Button>
        ))}
      </div>

      {/* Date range filter */}
      <div className="flex items-center">
        <DateRangeFilter onChange={onDateRangeChange} presets />
      </div>
    </div>
  )
}
