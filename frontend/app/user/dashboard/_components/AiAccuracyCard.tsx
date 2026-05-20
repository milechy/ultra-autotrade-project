'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
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

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-4">
      <h2 className="text-sm font-semibold text-zinc-400">AI的中率</h2>

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
        <p className="text-sm text-zinc-500 text-center py-4">データを取得できません</p>
      )}

      {!loading && data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <AccuracyValue value={data.accuracy_pct} label="全体的中率" />
            <AccuracyValue value={data.last_30d_accuracy_pct} label="直近30日" />
          </div>
          {data.total_decisions > 0 ? (
            <p className="text-xs text-zinc-500 text-center">
              {data.total_decisions}回提案、{data.correct_count}回でプラス
            </p>
          ) : (
            <p className="text-xs text-zinc-500 text-center">AI判定データがありません</p>
          )}
          {data.history && data.history.length > 0 && (
            <AccuracyChart data={data.history} />
          )}
        </>
      )}
    </div>
  )
}
