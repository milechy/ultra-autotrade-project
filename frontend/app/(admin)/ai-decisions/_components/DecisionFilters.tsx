'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
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
  const t = useTranslations('AdminDecisionFilters')

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
        {t('title')}
      </h3>
      <div className="space-y-3">
        {/* Action filter buttons */}
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">
            {t('labelActionFilter')}
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
            {t('labelConfidenceRange')}
          </label>
          <Select
            value={filters.confidenceRange}
            onValueChange={(v) => setConfidenceRange(v as ConfidenceRange)}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">{t('confidenceAll')}</SelectItem>
              <SelectItem value="0-50">{t('confidence0to50')}</SelectItem>
              <SelectItem value="50-70">{t('confidence50to70')}</SelectItem>
              <SelectItem value="70-100">{t('confidence70to100')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Agree filter */}
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">
            {t('labelAgreeFilter')}
          </label>
          <Select
            value={filters.agreeFilter}
            onValueChange={(v) => setAgreeFilter(v as AgreeFilter)}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">{t('agreeAll')}</SelectItem>
              <SelectItem value="agreed">{t('agreeAgreedOnly')}</SelectItem>
              <SelectItem value="disagreed">{t('agreeDisagreedOnly')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <button
          onClick={() =>
            onChange({ action: 'ALL', confidenceRange: 'ALL', agreeFilter: 'ALL' })
          }
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          {t('resetFilters')}
        </button>
      </div>
    </div>
  )
}
