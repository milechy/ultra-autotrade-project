'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export interface RiskSettings {
  hfWarning: number
  hfHardStop: number
  maxSingleTrade: number
  maxDailyTrade: number
  cooldownSeconds: number
}

interface RiskEngineSectionProps {
  settings: RiskSettings
  onChange: (settings: RiskSettings) => void
}

interface NumberFieldProps {
  label: string
  value: number
  suffix?: string
  step?: number
  min?: number
  max?: number
  warning?: string
  onChange: (v: number) => void
}

function NumberField({
  label,
  value,
  suffix,
  step = 1,
  min,
  max,
  warning,
  onChange,
}: NumberFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
        <Label className="text-gray-400 text-sm w-40 shrink-0">{label}</Label>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            step={step}
            min={min}
            max={max}
            value={value}
            onChange={(e) => {
              const parsed = parseFloat(e.target.value)
              if (!isNaN(parsed)) onChange(parsed)
            }}
            className="w-28 bg-gray-800 border-gray-700 text-gray-100 text-sm"
          />
          {suffix && (
            <span className="text-gray-400 text-sm shrink-0">{suffix}</span>
          )}
        </div>
      </div>
      {warning && (
        <p className="text-yellow-500 text-xs ml-0 sm:ml-44">{warning}</p>
      )}
    </div>
  )
}

export function RiskEngineSection({ settings, onChange }: RiskEngineSectionProps) {
  const t = useTranslations('RiskEngineSection')

  const update = <K extends keyof RiskSettings>(key: K, value: RiskSettings[K]) => {
    onChange({ ...settings, [key]: value })
  }

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-gray-100 text-base font-semibold">
          {t('sectionTitle')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* TODO: PUT /api/settings/risk */}
        <NumberField
          label={t('labelHfWarning')}
          value={settings.hfWarning}
          step={0.1}
          min={1.0}
          max={5.0}
          onChange={(v) => update('hfWarning', v)}
        />
        <NumberField
          label={t('labelHfHardStop')}
          value={settings.hfHardStop}
          step={0.1}
          min={1.0}
          max={5.0}
          warning={t('warningHfHardStop')}
          onChange={(v) => update('hfHardStop', v)}
        />
        <NumberField
          label={t('labelMaxSingleTrade')}
          value={settings.maxSingleTrade}
          suffix={t('suffixPercent')}
          step={1}
          min={1}
          max={100}
          onChange={(v) => update('maxSingleTrade', v)}
        />
        <NumberField
          label={t('labelMaxDailyTrade')}
          value={settings.maxDailyTrade}
          suffix={t('suffixPercent')}
          step={1}
          min={1}
          max={100}
          onChange={(v) => update('maxDailyTrade', v)}
        />
        <NumberField
          label={t('labelCooldown')}
          value={settings.cooldownSeconds}
          suffix={t('suffixSeconds')}
          step={60}
          min={0}
          onChange={(v) => update('cooldownSeconds', v)}
        />
      </CardContent>
    </Card>
  )
}
