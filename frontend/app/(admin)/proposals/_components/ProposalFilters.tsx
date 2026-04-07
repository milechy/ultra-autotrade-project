'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

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
  function set<K extends keyof ProposalFiltersState>(key: K, value: ProposalFiltersState[K]) {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">フィルター</h3>
      <div className="flex flex-wrap gap-3">
        {/* Status */}
        <Select
          value={filters.status}
          onValueChange={(v) => set('status', v as StatusFilter)}
        >
          <SelectTrigger className="h-8 w-40 text-xs">
            <SelectValue placeholder="ステータス" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL" className="text-xs">すべて</SelectItem>
            <SelectItem value="pending" className="text-xs">保留中</SelectItem>
            <SelectItem value="approved" className="text-xs">承認済み</SelectItem>
            <SelectItem value="rejected" className="text-xs">拒否</SelectItem>
            <SelectItem value="executed" className="text-xs">実行済み</SelectItem>
            <SelectItem value="expired" className="text-xs">期限切れ</SelectItem>
          </SelectContent>
        </Select>

        {/* Operation */}
        <Select
          value={filters.operation}
          onValueChange={(v) => set('operation', v as OperationFilter)}
        >
          <SelectTrigger className="h-8 w-40 text-xs">
            <SelectValue placeholder="操作種別" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL" className="text-xs">すべての操作</SelectItem>
            <SelectItem value="SUPPLY" className="text-xs">SUPPLY</SelectItem>
            <SelectItem value="WITHDRAW" className="text-xs">WITHDRAW</SelectItem>
            <SelectItem value="BORROW" className="text-xs">BORROW</SelectItem>
            <SelectItem value="REPAY" className="text-xs">REPAY</SelectItem>
          </SelectContent>
        </Select>

        {/* User search */}
        <Input
          placeholder="ユーザー名 / メールで検索..."
          value={filters.userSearch}
          onChange={(e) => set('userSearch', e.target.value)}
          className="h-8 w-52 text-xs"
        />

        {/* Date from */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-500 whitespace-nowrap">From</span>
          <Input
            type="date"
            value={filters.dateFrom}
            onChange={(e) => set('dateFrom', e.target.value)}
            className="h-8 w-36 text-xs"
          />
        </div>

        {/* Date to */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-500 whitespace-nowrap">To</span>
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
          リセット
        </button>
      </div>
    </div>
  )
}
