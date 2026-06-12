// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useTranslations } from 'next-intl'

type UserMode = 'managed' | 'active' | 'pro'

const MODE_OPTIONS = [
  {
    value: 'managed' as UserMode,
    labelKey: 'managedLabel',
    descKey: 'managedDesc',
    borderColor: 'border-green-600 bg-green-950/40',
    ringColor: 'ring-2 ring-green-500',
  },
  {
    value: 'active' as UserMode,
    labelKey: 'activeLabel',
    descKey: 'activeDesc',
    borderColor: 'border-yellow-600 bg-yellow-950/40',
    ringColor: 'ring-2 ring-yellow-500',
  },
  {
    value: 'pro' as UserMode,
    labelKey: 'proLabel',
    descKey: 'proDesc',
    borderColor: 'border-blue-600 bg-blue-950/40',
    ringColor: 'ring-2 ring-blue-500',
  },
] as const

interface OperationModeSelectorProps {
  currentMode: string
  onModeChange: (mode: string) => void
  disabled?: boolean
}

export function OperationModeSelector({
  currentMode,
  onModeChange,
  disabled = false,
}: OperationModeSelectorProps) {
  const t = useTranslations('OperationMode')

  return (
    <div className="space-y-2" data-testid="mode-selector">
      {MODE_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          disabled={disabled}
          onClick={() => onModeChange(option.value)}
          data-mode={option.value}
          className={`w-full text-left rounded-lg border p-3 transition-all ${option.borderColor} ${
            currentMode === option.value
              ? option.ringColor
              : 'opacity-60 hover:opacity-90'
          } ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
        >
          <p className="text-sm font-medium text-zinc-100">{t(option.labelKey)}</p>
          <p className="text-xs text-zinc-400 mt-0.5">{t(option.descKey)}</p>
        </button>
      ))}
    </div>
  )
}
