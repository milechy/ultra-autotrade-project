'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import type { AccuracyPoint } from '@/components/charts/AccuracyChart'

const AccuracyChart = dynamic(() => import('@/components/charts/AccuracyChart'), { ssr: false })

interface AiAccuracyResponse {
  accuracy_pct: number | null
  last_30d_accuracy_pct: number | null
  total_decisions: number
  correct_count: number
  history?: AccuracyPoint[]
}

function AccuracyValue({ value, label }: { value: number | null; label: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-800/60 px-4 py-3 space-y-1">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="text-2xl font-bold">
        {value === null ? (
          <span className="text-zinc-500">—</span>
        ) : (
          <span className={value < 0 ? 'text-red-500' : 'text-white'}>
            {Number(value).toFixed(1)}%
          </span>
        )}
      </p>
    </div>
  )
}

export function AiAccuracyCard() {
  const { data, loading, error } = useAuthFetch<AiAccuracyResponse>('/api/ai/accuracy')
  const t = useTranslations('Dashboard')

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-4">
      <h2 className="text-sm font-semibold text-zinc-400">{t('aiAccuracyTitle')}</h2>

      {loading && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="h-16 rounded-xl" />
            <Skeleton className="h-16 rounded-xl" />
          </div>
          <Skeleton className="h-[240px] rounded-xl" />
        </div>
      )}

      {!loading && (error || !data) && (
        <p className="text-sm text-zinc-500 text-center py-4">{t('fetchError')}</p>
      )}

      {!loading && data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <AccuracyValue value={data.accuracy_pct} label={t('overallAccuracy')} />
            <AccuracyValue value={data.last_30d_accuracy_pct} label={t('last30dAccuracy')} />
          </div>
          {data.total_decisions > 0 ? (
            <p className="text-xs text-zinc-500 text-center">
              {t('accuracySummary', { total: data.total_decisions, correct: data.correct_count })}
            </p>
          ) : (
            <p className="text-xs text-zinc-500 text-center">{t('noAccuracyData')}</p>
          )}
          {data.history && data.history.length > 0 && (
            <AccuracyChart data={data.history} />
          )}
        </>
      )}
    </div>
  )
}
