'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export type ActionFilter = 'ALL' | 'BUY' | 'SELL' | 'HOLD'
export type ConfidenceRange = 'ALL' | '0-50' | '50-70' | '70-100'
export type AgreeFilter = 'ALL' | 'agreed' | 'disagreed'

export interface DecisionFiltersState {
  action: ActionFilter
  confidenceRange: ConfidenceRange
  agreeFilter: AgreeFilter
}

interface DecisionFiltersProps {
  filters: DecisionFiltersState
  onChange: (filters: DecisionFiltersState) => void
}

const ACTION_BUTTONS: { label: string; value: ActionFilter }[] = [
  { label: 'ALL', value: 'ALL' },
  { label: 'BUY', value: 'BUY' },
  { label: 'SELL', value: 'SELL' },
  { label: 'HOLD', value: 'HOLD' },
]

export function DecisionFilters({ filters, onChange }: DecisionFiltersProps) {
  function setAction(value: ActionFilter) {
    onChange({ ...filters, action: value })
  }

  function setConfidenceRange(value: ConfidenceRange) {
    onChange({ ...filters, confidenceRange: value })
  }

  function setAgreeFilter(value: AgreeFilter) {
    onChange({ ...filters, agreeFilter: value })
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
        フィルター
      </h3>
      <div className="space-y-3">
        {/* Action filter buttons */}
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">
            アクション別
          </label>
          <div className="flex gap-1 flex-wrap">
            {ACTION_BUTTONS.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => setAction(value)}
                className={`px-3 py-1 text-xs font-medium rounded-md border transition-colors ${
                  filters.action === value
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Confidence range */}
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">
            信頼度範囲
          </label>
          <Select
            value={filters.confidenceRange}
            onValueChange={(v) => setConfidenceRange(v as ConfidenceRange)}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">全範囲</SelectItem>
              <SelectItem value="0-50">0〜50%</SelectItem>
              <SelectItem value="50-70">50〜70%</SelectItem>
              <SelectItem value="70-100">70〜100%</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Agree filter */}
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">
            一致/不一致
          </label>
          <Select
            value={filters.agreeFilter}
            onValueChange={(v) => setAgreeFilter(v as AgreeFilter)}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">ALL</SelectItem>
              <SelectItem value="agreed">一致のみ</SelectItem>
              <SelectItem value="disagreed">不一致のみ</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <button
          onClick={() =>
            onChange({ action: 'ALL', confidenceRange: 'ALL', agreeFilter: 'ALL' })
          }
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          フィルターをリセット
        </button>
      </div>
    </div>
  )
}
