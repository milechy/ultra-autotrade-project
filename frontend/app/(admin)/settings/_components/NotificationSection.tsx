'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export interface NotificationSettings {
  slackWebhookUrl: string
  lineToken: string
  notificationLevel: string
}

interface NotificationSectionProps {
  settings: NotificationSettings
  onChange: (settings: NotificationSettings) => void
}

const NOTIFICATION_LEVELS = [
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ALERT', label: 'ALERT' },
  { value: 'CRITICAL', label: 'CRITICAL' },
  { value: 'EMERGENCY', label: 'EMERGENCY' },
]

function maskSecret(value: string): string {
  if (!value) return ''
  if (value.length <= 10) return '••••••••••'
  return value.slice(0, 6) + '•'.repeat(Math.min(value.length - 10, 20)) + value.slice(-4)
}

interface MaskedInputProps {
  label: string
  value: string
  onChange: (v: string) => void
  onTest: () => void
  testLabel: string
  testLoading: boolean
  sendingLabel: string
  revealLabel: string
  hideLabel: string
}

function MaskedInput({
  label,
  value,
  onChange,
  onTest,
  testLabel,
  testLoading,
  sendingLabel,
  revealLabel,
  hideLabel,
}: MaskedInputProps) {
  const [revealed, setRevealed] = useState(false)

  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-gray-400 text-sm">{label}</Label>
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1 max-w-sm">
          <Input
            type={revealed ? 'text' : 'password'}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="bg-gray-800 border-gray-700 text-gray-100 text-sm pr-16"
          />
          <button
            type="button"
            onClick={() => setRevealed((r) => !r)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {revealed ? hideLabel : revealLabel}
          </button>
        </div>
        {!revealed && value && (
          <span className="self-center text-xs text-gray-500 font-mono">
            {maskSecret(value)}
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={onTest}
          disabled={testLoading || !value}
          className="border-gray-700 text-gray-300 hover:bg-gray-800 shrink-0"
        >
          {testLoading ? sendingLabel : testLabel}
        </Button>
      </div>
    </div>
  )
}

export function NotificationSection({ settings, onChange }: NotificationSectionProps) {
  const t = useTranslations('AdminNotification')
  const [slackTesting, setSlackTesting] = useState(false)
  const [lineTesting, setLineTesting] = useState(false)

  const update = <K extends keyof NotificationSettings>(
    key: K,
    value: NotificationSettings[K],
  ) => {
    onChange({ ...settings, [key]: value })
  }

  const handleSlackTest = async () => {
    setSlackTesting(true)
    try {
      // TODO: POST /api/settings/notifications/test/slack
      await new Promise<void>((resolve) => setTimeout(resolve, 800))
      alert(t('slackTestSent'))
    } finally {
      setSlackTesting(false)
    }
  }

  const handleLineTest = async () => {
    setLineTesting(true)
    try {
      // TODO: POST /api/settings/notifications/test/line
      await new Promise<void>((resolve) => setTimeout(resolve, 800))
      alert(t('lineTestSent'))
    } finally {
      setLineTesting(false)
    }
  }

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-gray-100 text-base font-semibold">{t('title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* TODO: PUT /api/settings/notifications */}
        <MaskedInput
          label="Slack Webhook URL"
          value={settings.slackWebhookUrl}
          onChange={(v) => update('slackWebhookUrl', v)}
          onTest={handleSlackTest}
          testLabel={t('testSendBtn')}
          testLoading={slackTesting}
          sendingLabel={t('sendingBtn')}
          revealLabel={t('revealBtn')}
          hideLabel={t('hideBtn')}
        />
        <MaskedInput
          label={t('lineTokenLabel')}
          value={settings.lineToken}
          onChange={(v) => update('lineToken', v)}
          onTest={handleLineTest}
          testLabel={t('testSendBtn')}
          testLoading={lineTesting}
          sendingLabel={t('sendingBtn')}
          revealLabel={t('revealBtn')}
          hideLabel={t('hideBtn')}
        />

        {/* 通知レベル閾値 */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
          <Label className="text-gray-400 text-sm w-36 shrink-0">{t('labelNotificationLevel')}</Label>
          <Select
            value={settings.notificationLevel}
            onValueChange={(v) => update('notificationLevel', v)}
          >
            <SelectTrigger className="w-40 bg-gray-800 border-gray-700 text-gray-100">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-gray-800 border-gray-700 text-gray-100">
              {NOTIFICATION_LEVELS.map((opt) => (
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
        </div>
      </CardContent>
    </Card>
  )
}
