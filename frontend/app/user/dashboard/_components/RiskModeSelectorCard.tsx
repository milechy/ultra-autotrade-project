'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { Lock, Check } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import { apiPut } from '@/lib/api/client'
import { useTranslations } from 'next-intl'

type RiskMode = 'conservative' | 'balanced' | 'aggressive'

interface RiskModeOption {
  mode: RiskMode
  label: string
  phase: number
  allowed_in_phase_1: boolean
  subscription_rate: string
  protocols: string[]
}

interface RiskModesResponse {
  modes: RiskModeOption[]
}

interface RiskModeCurrentResponse {
  mode: RiskMode
  label: string
}

export interface RiskModeSelectorCardProps {
  readOnly?: boolean
}

const MODE_STYLE: Record<RiskMode, { active: string; hover: string; icon: string }> = {
  conservative: {
    active: 'border-emerald-500 bg-emerald-950/20',
    hover: 'border-zinc-700 hover:border-emerald-700',
    icon: '🛡️',
  },
  balanced: {
    active: 'border-blue-500 bg-blue-950/20',
    hover: 'border-zinc-700 hover:border-blue-700',
    icon: '⚖️',
  },
  aggressive: {
    active: 'border-orange-500 bg-orange-950/20',
    hover: 'border-zinc-700 hover:border-orange-700',
    icon: '🚀',
  },
}

function formatSubscriptionRate(rate: string, freeLabel: string): string {
  const n = Number(rate)
  if (n === 0) return freeLabel
  return `${(n * 100).toFixed(1)}%/月`
}

export function RiskModeSelectorCard({ readOnly = false }: RiskModeSelectorCardProps) {
  const t = useTranslations('RiskModeSelector')
  const { data: current, refetch: refetchCurrent } = useAuthFetch<RiskModeCurrentResponse>('/auth/risk-mode')
  const { data: modesData, loading } = useAuthFetch<RiskModesResponse>('/auth/risk-modes')
  const [saving, setSaving] = useState(false)

  const currentMode = current?.mode ?? null

  const handleChange = async (mode: RiskMode) => {
    if (readOnly || saving || mode === currentMode) return
    setSaving(true)
    try {
      await apiPut('/auth/risk-mode', { mode })
      await refetchCurrent()
      const label = modesData?.modes.find((m) => m.mode === mode)?.label ?? mode
      toast.success(t('changeSuccess', { mode: label }))
    } catch {
      toast.error(t('changeError'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="risk-mode-selector-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base text-zinc-100">{t('title')}</CardTitle>
          {readOnly && (
            <span className="text-xs text-zinc-500">{t('readOnly')}</span>
          )}
        </div>
        <p className="text-xs text-zinc-500">{t('subtitle')}</p>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-28 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {(modesData?.modes ?? []).map((opt) => {
              const isActive = currentMode === opt.mode
              const isLocked = !opt.allowed_in_phase_1
              const style = MODE_STYLE[opt.mode]
              const isInteractive = !readOnly && !isLocked && !saving

              return (
                <button
                  key={opt.mode}
                  onClick={() => { if (isInteractive) void handleChange(opt.mode) }}
                  disabled={!isInteractive}
                  data-testid={`risk-mode-option-${opt.mode}`}
                  aria-pressed={isActive}
                  className={cn(
                    'relative text-left rounded-lg border-2 p-3 transition-all',
                    isActive ? style.active : style.hover,
                    (isLocked || readOnly) && 'cursor-default',
                    saving && !isLocked && !readOnly && 'opacity-60 cursor-not-allowed',
                  )}
                >
                  {/* Lock badge (Phase 2 予定) */}
                  {isLocked && (
                    <div className="absolute top-2 right-2 flex items-center gap-0.5">
                      <Lock className="h-3 w-3 text-zinc-500" />
                      <span className="text-[10px] text-zinc-500">{t('locked')}</span>
                    </div>
                  )}

                  {/* Mode label row */}
                  <div className="flex items-center gap-1.5 mb-2 pr-14">
                    <span className="text-base leading-none">{style.icon}</span>
                    <span className="text-sm font-semibold text-zinc-100 leading-none">{opt.label}</span>
                    {isActive && (
                      <span className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 leading-none">
                        <Check className="h-2.5 w-2.5" />
                        {t('current')}
                      </span>
                    )}
                  </div>

                  {/* Subscription rate */}
                  <div className="mb-1.5">
                    <span className="text-xs text-zinc-500">{t('subscriptionRate')}: </span>
                    <span className="text-xs font-semibold text-zinc-200">
                      {formatSubscriptionRate(opt.subscription_rate, t('free'))}
                    </span>
                  </div>

                  {/* Protocols */}
                  <div className="flex flex-wrap gap-1">
                    {opt.protocols.sort().map((p) => (
                      <Badge
                        key={p}
                        variant="outline"
                        className="text-[10px] px-1.5 py-0 h-4 border-zinc-700 text-zinc-400 font-normal"
                      >
                        {p}
                      </Badge>
                    ))}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
