'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export type StatusFilter = 'ALL' | 'pending' | 'approved' | 'rejected' | 'executed' | 'expired'
export type OperationFilter = 'ALL' | 'SUPPLY' | 'WITHDRAW' | 'BORROW' | 'REPAY'

export interface ProposalFiltersState {
  status: StatusFilter
  operation: OperationFilter
  userSearch: string
  dateFrom: string
  dateTo: string
}

interface ProposalFiltersProps {
  filters: ProposalFiltersState
  onChange: (next: ProposalFiltersState) => void
}

export function ProposalFilters({ filters, onChange }: ProposalFiltersProps) {
  const t = useTranslations('AdminProposalFilters')

  function set<K extends keyof ProposalFiltersState>(key: K, value: ProposalFiltersState[K]) {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{t('heading')}</h3>
      <div className="flex flex-wrap gap-3">
        {/* Status */}
        <Select
          value={filters.status}
          onValueChange={(v) => set('status', v as StatusFilter)}
        >
          <SelectTrigger className="h-8 w-40 text-xs">
            <SelectValue placeholder={t('statusPlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL" className="text-xs">{t('statusAll')}</SelectItem>
            <SelectItem value="pending" className="text-xs">{t('statusPending')}</SelectItem>
            <SelectItem value="approved" className="text-xs">{t('statusApproved')}</SelectItem>
            <SelectItem value="rejected" className="text-xs">{t('statusRejected')}</SelectItem>
            <SelectItem value="executed" className="text-xs">{t('statusExecuted')}</SelectItem>
            <SelectItem value="expired" className="text-xs">{t('statusExpired')}</SelectItem>
          </SelectContent>
        </Select>

        {/* Operation */}
        <Select
          value={filters.operation}
          onValueChange={(v) => set('operation', v as OperationFilter)}
        >
          <SelectTrigger className="h-8 w-40 text-xs">
            <SelectValue placeholder={t('operationPlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL" className="text-xs">{t('operationAll')}</SelectItem>
            <SelectItem value="SUPPLY" className="text-xs">{t('opSupply')}</SelectItem>
            <SelectItem value="WITHDRAW" className="text-xs">{t('opWithdraw')}</SelectItem>
            <SelectItem value="BORROW" className="text-xs">{t('opBorrow')}</SelectItem>
            <SelectItem value="REPAY" className="text-xs">{t('opRepay')}</SelectItem>
          </SelectContent>
        </Select>

        {/* User search */}
        <Input
          placeholder={t('userSearchPlaceholder')}
          value={filters.userSearch}
          onChange={(e) => set('userSearch', e.target.value)}
          className="h-8 w-52 text-xs"
        />

        {/* Date from */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-500 whitespace-nowrap">{t('dateFrom')}</span>
          <Input
            type="date"
            value={filters.dateFrom}
            onChange={(e) => set('dateFrom', e.target.value)}
            className="h-8 w-36 text-xs"
          />
        </div>

        {/* Date to */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-500 whitespace-nowrap">{t('dateTo')}</span>
          <Input
            type="date"
            value={filters.dateTo}
            onChange={(e) => set('dateTo', e.target.value)}
            className="h-8 w-36 text-xs"
          />
        </div>

        <button
          onClick={() =>
            onChange({
              status: 'ALL',
              operation: 'ALL',
              userSearch: '',
              dateFrom: '',
              dateTo: '',
            })
          }
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline self-center"
        >
          {t('reset')}
        </button>
      </div>
    </div>
  )
}
