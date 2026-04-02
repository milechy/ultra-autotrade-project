// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

type UserMode = 'managed' | 'active' | 'pro'

const MODE_OPTIONS: {
  value: UserMode
  label: string
  description: string
  borderColor: string
  ringColor: string
}[] = [
  {
    value: 'managed',
    label: 'フルオート',
    description: 'AIが全自動で判断・実行。初心者向け。',
    borderColor: 'border-green-600 bg-green-950/40',
    ringColor: 'ring-2 ring-green-500',
  },
  {
    value: 'active',
    label: 'セミオート',
    description: 'AIが提案→ユーザーが承認→実行。中級者向け。',
    borderColor: 'border-yellow-600 bg-yellow-950/40',
    ringColor: 'ring-2 ring-yellow-500',
  },
  {
    value: 'pro',
    label: 'マニュアル',
    description: 'AIが提案→手動判断。上級者向け。',
    borderColor: 'border-blue-600 bg-blue-950/40',
    ringColor: 'ring-2 ring-blue-500',
  },
]

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
          <p className="text-sm font-medium text-zinc-100">{option.label}</p>
          <p className="text-xs text-zinc-400 mt-0.5">{option.description}</p>
        </button>
      ))}
    </div>
  )
}
