'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SafetyScoreGauge } from '@/components/shared'
import { apiFetch } from '@/lib/api/client'

interface SafetyScoreBreakdown {
  util_score: string
  hf_score: string
  vol_score: string
}

interface SafetyScoreData {
  score: string
  label: string
  color: string
  breakdown: SafetyScoreBreakdown
}

export function SafetyScore() {
  const [scoreData, setScoreData] = useState<SafetyScoreData | null>(null)
  const [loading, setLoading] = useState(true)
  const t = useTranslations('Dashboard')

  useEffect(() => {
    apiFetch<SafetyScoreData>('/api/transparency/safety-score')
      .then((data) => setScoreData(data))
      .catch(() => {
        // Fallback to default on error
        setScoreData(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const score = scoreData ? Math.round(parseFloat(scoreData.score)) : 85

  if (loading) {
    return (
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader className="pb-2 pt-4 px-4">
          <CardTitle className="text-sm font-medium text-zinc-400">{t('safetyScore')}</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="flex items-center gap-5">
            <div className="h-20 w-20 rounded-full bg-zinc-800 animate-pulse" />
            <div className="space-y-2">
              <div className="h-6 w-16 rounded bg-zinc-800 animate-pulse" />
              <div className="h-4 w-12 rounded bg-zinc-800 animate-pulse" />
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-sm font-medium text-zinc-400">{t('safetyScore')}</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <SafetyScoreGauge score={score} size="md" showLabel />
        <p className="text-xs text-zinc-500 mt-2">{t('safetyScoreRange')}</p>
      </CardContent>
    </Card>
  )
}
