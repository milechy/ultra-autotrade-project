// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { apiPut } from '@/lib/api/client'

type RiskMode = 'conservative' | 'balanced' | 'aggressive'

interface RiskModeResponse {
  mode: RiskMode
  message: string
}

interface RiskSettingsCardProps {
  riskMode: RiskMode
  onRiskModeChange: (mode: RiskMode) => void
  maxSingleTradeUsd: number
  onMaxSingleTradeUsdChange: (value: number) => void
  maxDailyTradeUsd: number
  onMaxDailyTradeUsdChange: (value: number) => void
}

const riskOptions: { mode: RiskMode; label: string; emoji: string; description: string }[] = [
  { mode: 'conservative', label: '保守的', emoji: '🛡️', description: '安全重視、低リスク' },
  { mode: 'balanced', label: 'バランス', emoji: '⚖️', description: '標準設定' },
  { mode: 'aggressive', label: '積極的', emoji: '🚀', description: '高リターン、高リスク' },
]

const modeActiveClass: Record<RiskMode, string> = {
  conservative: 'border-emerald-500 bg-emerald-950/20',
  balanced: 'border-blue-500 bg-blue-950/20',
  aggressive: 'border-orange-500 bg-orange-950/20',
}

export function RiskSettingsCard({
  riskMode,
  onRiskModeChange,
  maxSingleTradeUsd,
  onMaxSingleTradeUsdChange,
  maxDailyTradeUsd,
  onMaxDailyTradeUsdChange,
}: RiskSettingsCardProps) {
  const [saving, setSaving] = useState(false)

  const handleRiskModeChange = async (mode: RiskMode) => {
    if (saving || mode === riskMode) return
    setSaving(true)
    try {
      await apiPut<RiskModeResponse>('/auth/risk-mode', { mode })
      onRiskModeChange(mode)
      toast.success('リスクモードを保存しました')
    } catch {
      toast.error('リスクモードの保存に失敗しました')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-zinc-100">リスク設定</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* リスクモード選択 */}
        <div className="space-y-2">
          <Label className="text-zinc-300 text-sm">リスクモード</Label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {riskOptions.map((opt) => {
              const isActive = riskMode === opt.mode
              return (
                <button
                  key={opt.mode}
                  onClick={() => { void handleRiskModeChange(opt.mode) }}
                  disabled={saving}
                  className={cn(
                    'text-left rounded-lg border-2 p-3 transition-all disabled:opacity-60',
                    isActive
                      ? modeActiveClass[opt.mode]
                      : 'border-zinc-700 bg-zinc-800/40 hover:border-zinc-600'
                  )}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-base">{opt.emoji}</span>
                    <span className="text-sm font-semibold text-zinc-100">{opt.label}</span>
                    {isActive && (
                      <span className="ml-auto text-xs px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300">
                        現在
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-400">{opt.description}</p>
                </button>
              )
            })}
          </div>
        </div>

        {/* 最大単回取引額 */}
        <div className="space-y-1.5">
          <Label htmlFor="max-single-trade" className="text-zinc-300 text-sm">
            最大単回取引額 (USD)
          </Label>
          <Input
            id="max-single-trade"
            type="number"
            min={1}
            step={10}
            value={maxSingleTradeUsd}
            onChange={(e) => {
              onMaxSingleTradeUsdChange(Number(e.target.value))
              // TODO: Save to backend PUT /api/user/settings
            }}
            placeholder="500"
            className="bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-500"
          />
        </div>

        {/* 日次取引上限 */}
        <div className="space-y-1.5">
          <Label htmlFor="max-daily-trade" className="text-zinc-300 text-sm">
            日次取引上限 (USD)
          </Label>
          <Input
            id="max-daily-trade"
            type="number"
            min={1}
            step={100}
            value={maxDailyTradeUsd}
            onChange={(e) => {
              onMaxDailyTradeUsdChange(Number(e.target.value))
              // TODO: Save to backend PUT /api/user/settings
            }}
            placeholder="2000"
            className="bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-500"
          />
        </div>

        <p className="text-xs text-zinc-500">* 管理者設定の範囲内で調整できます</p>
      </CardContent>
    </Card>
  )
}
