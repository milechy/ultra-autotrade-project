'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'

export interface AISettings {
  frequency: string
  confidenceThreshold: number
  crossVerification: boolean
}

interface AISettingsSectionProps {
  settings: AISettings
  onChange: (settings: AISettings) => void
}

export function AISettingsSection({ settings, onChange }: AISettingsSectionProps) {
  const t = useTranslations('AdminAISettings')

  const FREQUENCY_OPTIONS = [
    { value: '1h', label: t('freq1h') },
    { value: '2h', label: t('freq2h') },
    { value: '4h', label: t('freq4h') },
    { value: '8h', label: t('freq8h') },
    { value: 'manual', label: t('freqManual') },
  ]

  const update = <K extends keyof AISettings>(key: K, value: AISettings[K]) => {
    onChange({ ...settings, [key]: value })
  }

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-gray-100 text-base font-semibold">{t('title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* 判定頻度 */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
          <Label className="text-gray-400 text-sm w-36 shrink-0">{t('labelFrequency')}</Label>
          <Select
            value={settings.frequency}
            onValueChange={(v) => update('frequency', v)}
          >
            <SelectTrigger className="w-40 bg-gray-800 border-gray-700 text-gray-100">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-gray-800 border-gray-700 text-gray-100">
              {FREQUENCY_OPTIONS.map((opt) => (
                <SelectItem
                  key={opt.value}
                  value={opt.value}
                  className="focus:bg-gray-700 focus:text-gray-100"
                >
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {/* TODO: PUT /api/settings/ai */}
        </div>

        {/* 信頼度閾値 */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <Label className="text-gray-400 text-sm">{t('labelConfidenceThreshold')}</Label>
            <span className="text-gray-200 text-sm font-semibold tabular-nums">
              {settings.confidenceThreshold}
            </span>
          </div>
          <Slider
            min={0}
            max={100}
            step={1}
            value={[settings.confidenceThreshold]}
            onValueChange={([v]) => update('confidenceThreshold', v)}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-600">
            <span>0</span>
            <span>50</span>
            <span>100</span>
          </div>
        </div>

        {/* クロス検証 */}
        <div className="flex items-center gap-4">
          <Label className="text-gray-400 text-sm w-36 shrink-0">{t('labelCrossVerification')}</Label>
          <div className="flex items-center gap-3">
            <Switch
              checked={settings.crossVerification}
              onCheckedChange={(v) => update('crossVerification', v)}
            />
            <span className="text-sm text-gray-300">
              {settings.crossVerification ? 'ON' : 'OFF'}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
