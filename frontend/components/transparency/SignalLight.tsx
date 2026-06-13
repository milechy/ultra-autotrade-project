'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import type { SignalData } from './types'

interface SignalLightProps {
  signal: SignalData
  className?: string
}

const WEATHER_CONFIG = {
  sunny: {
    emoji: '☀️',
    bg: 'bg-green-50 dark:bg-green-950',
    border: 'border-green-200 dark:border-green-800',
    label_color: 'text-green-700 dark:text-green-300',
    pulse: false,
  },
  partly_cloudy: {
    emoji: '⛅',
    bg: 'bg-yellow-50 dark:bg-yellow-950',
    border: 'border-yellow-200 dark:border-yellow-800',
    label_color: 'text-yellow-700 dark:text-yellow-300',
    pulse: false,
  },
  cloudy: {
    emoji: '☁️',
    bg: 'bg-gray-50 dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    label_color: 'text-gray-700 dark:text-gray-300',
    pulse: false,
  },
  stormy: {
    emoji: '⛈️',
    bg: 'bg-red-50 dark:bg-red-950',
    border: 'border-red-200 dark:border-red-800',
    label_color: 'text-red-700 dark:text-red-300',
    pulse: true,
  },
}

export function SignalLight({ signal, className }: SignalLightProps) {
  const t = useTranslations('TransparencySignalLight')
  if (!signal || !signal.weather) return null
  const config = WEATHER_CONFIG[signal.weather as keyof typeof WEATHER_CONFIG] ?? WEATHER_CONFIG.cloudy

  return (
    <Card className={cn(config.bg, config.border, 'border-2', className)}>
      <CardContent className="flex flex-col items-center gap-3 p-6">
        <span className={cn('text-5xl', config.pulse && 'animate-pulse')}>
          {config.emoji}
        </span>
        <div className="text-center">
          <p className={cn('text-xl font-bold', config.label_color)}>
            {signal.label}
          </p>
          <p className="text-sm text-muted-foreground mt-1">
            {signal.description}
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>{t('confidenceLabel')}</span>
          <span className="font-semibold">{signal.confidence}%</span>
        </div>
        {signal.updated_at && (
          <p className="text-xs text-muted-foreground">
            {t('updatedLabel')} {new Date(signal.updated_at).toLocaleString('ja-JP')}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
