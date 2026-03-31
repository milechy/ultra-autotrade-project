// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

type NotificationFrequency = 'all' | 'important' | 'emergency'

interface NotificationCardProps {
  email: string
  onEmailChange: (value: string) => void
  frequency: NotificationFrequency
  onFrequencyChange: (value: NotificationFrequency) => void
}

const frequencyOptions: { value: NotificationFrequency; label: string; description: string }[] = [
  { value: 'all', label: '全ての通知', description: 'AI判定ごと' },
  { value: 'important', label: '重要な通知のみ', description: 'WARNING以上' },
  { value: 'emergency', label: '緊急時のみ', description: 'EMERGENCY' },
]

export function NotificationCard({
  email,
  onEmailChange,
  frequency,
  onFrequencyChange,
}: NotificationCardProps) {
  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-zinc-100">通知設定</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* メールアドレス */}
        <div className="space-y-1.5">
          <Label htmlFor="notification-email" className="text-zinc-300 text-sm">
            メールアドレス
          </Label>
          <Input
            id="notification-email"
            type="email"
            value={email}
            onChange={(e) => {
              onEmailChange(e.target.value)
              // TODO: Save to backend PUT /api/user/settings
            }}
            placeholder="email@example.com"
            className="bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-500"
          />
        </div>

        {/* 通知頻度 */}
        <div className="space-y-2">
          <Label className="text-zinc-300 text-sm">通知頻度</Label>
          <RadioGroup
            value={frequency}
            onValueChange={(v) => {
              onFrequencyChange(v as NotificationFrequency)
              // TODO: Save to backend PUT /api/user/settings
              toast('設定を保存しました')
            }}
            name="notification-frequency"
            className="space-y-2"
          >
            {frequencyOptions.map((opt) => (
              <div
                key={opt.value}
                className={cn(
                  'flex items-center gap-3 rounded-lg border p-3 cursor-pointer transition-colors',
                  frequency === opt.value
                    ? 'border-blue-500 bg-blue-950/20'
                    : 'border-zinc-700 bg-zinc-800/40 hover:border-zinc-600'
                )}
                onClick={() => {
                  onFrequencyChange(opt.value)
                  // TODO: Save to backend PUT /api/user/settings
                  toast('設定を保存しました')
                }}
              >
                <RadioGroupItem
                  value={opt.value}
                  id={`freq-${opt.value}`}
                />
                <div className="flex-1">
                  <label
                    htmlFor={`freq-${opt.value}`}
                    className="text-sm font-medium text-zinc-100 cursor-pointer"
                  >
                    {opt.label}
                  </label>
                  <p className="text-xs text-zinc-400">{opt.description}</p>
                </div>
              </div>
            ))}
          </RadioGroup>
        </div>
      </CardContent>
    </Card>
  )
}
