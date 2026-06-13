'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface DateRangeFilterProps {
  onChange: (range: { from: Date; to: Date } | 'all') => void
  presets?: boolean
}

type PresetKey = '7d' | '30d' | '90d' | 'all'

const presetKeys: PresetKey[] = ['7d', '30d', '90d', 'all']

function getPresetRange(key: PresetKey): { from: Date; to: Date } | 'all' {
  if (key === 'all') return 'all'
  const days = { '7d': 7, '30d': 30, '90d': 90 }[key]
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - days)
  return { from, to }
}

function toInputDate(date: Date): string {
  return date.toISOString().split('T')[0]
}

const presetLabelKey: Record<PresetKey, 'days7' | 'days30' | 'days90' | 'all'> = {
  '7d': 'days7',
  '30d': 'days30',
  '90d': 'days90',
  'all': 'all',
}

export function DateRangeFilter({ onChange, presets = true }: DateRangeFilterProps) {
  const t = useTranslations('SharedDateRangeFilter')
  const [activePreset, setActivePreset] = useState<PresetKey | null>('30d')
  const today = new Date()
  const thirtyDaysAgo = new Date()
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30)

  const [fromDate, setFromDate] = useState<string>(toInputDate(thirtyDaysAgo))
  const [toDate, setToDate] = useState<string>(toInputDate(today))

  const handlePreset = (key: PresetKey) => {
    setActivePreset(key)
    const range = getPresetRange(key)
    if (range !== 'all') {
      setFromDate(toInputDate(range.from))
      setToDate(toInputDate(range.to))
    }
    onChange(range)
  }

  const handleCustomChange = (from: string, to: string) => {
    setActivePreset(null)
    if (from && to) {
      onChange({ from: new Date(from), to: new Date(to) })
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {presets && (
        <div className="flex items-center gap-1">
          {presetKeys.map((key) => (
            <Button
              key={key}
              variant={activePreset === key ? 'default' : 'outline'}
              size="sm"
              onClick={() => handlePreset(key)}
              className={cn(
                'h-8 px-3 text-xs',
                activePreset === key && 'font-semibold'
              )}
            >
              {t(presetLabelKey[key])}
            </Button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1.5 text-sm">
        <input
          type="date"
          value={fromDate}
          onChange={(e) => {
            setFromDate(e.target.value)
            handleCustomChange(e.target.value, toDate)
          }}
          className="h-8 rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <span className="text-muted-foreground">〜</span>
        <input
          type="date"
          value={toDate}
          onChange={(e) => {
            setToDate(e.target.value)
            handleCustomChange(fromDate, e.target.value)
          }}
          className="h-8 rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
    </div>
  )
}
