'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/api/client'

const AssetChartRecharts = dynamic(() => import('./AssetChartRecharts'), { ssr: false })

type Period = 'daily' | 'weekly' | 'monthly'

const PERIOD_VALUES: Period[] = ['daily', 'weekly', 'monthly']

interface DataPoint {
  date: string
  value: number
}

interface PortfolioHistoryResponse {
  items: Array<{ total_value_usd: string; recorded_at: string }>
  total: number
  period: string
  interval: string
}

export function AssetChart() {
  const { token, isLoading: authLoading } = useAuth()
  const t = useTranslations('Dashboard')
  const [period, setPeriod] = useState<Period>('daily')
  const [data, setData] = useState<DataPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const fetchData = useCallback(async () => {
    if (!token) return
    setError(false)
    setLoading(true)
    try {
      const res = await apiFetch<PortfolioHistoryResponse>(
        `/api/portfolio/history?period=${period}`,
      )
      const mapped: DataPoint[] = (res?.items ?? []).map((item) => ({
        date: new Date(item.recorded_at).toLocaleDateString('ja-JP', {
          month: 'short',
          day: 'numeric',
        }),
        value: parseFloat(item.total_value_usd),
      }))
      setData(mapped)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [period, token])

  useEffect(() => {
    if (authLoading) return
    fetchData()
  }, [fetchData, authLoading])

  // 30-second auto-refresh — only when authenticated
  useEffect(() => {
    if (!token) return
    const id = setInterval(() => fetchData(), 30_000)
    return () => clearInterval(id)
  }, [fetchData, token])

  const periodLabels: Record<Period, string> = {
    daily: t('periodDaily'),
    weekly: t('periodWeekly'),
    monthly: t('periodMonthly'),
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-800/40 p-1 w-fit">
        {PERIOD_VALUES.map((value) => (
          <button
            key={value}
            onClick={() => setPeriod(value)}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              period === value
                ? 'bg-zinc-700 text-white'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {periodLabels[value]}
          </button>
        ))}
      </div>
      {authLoading || loading ? (
        <Skeleton className="h-[200px] rounded-xl" />
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-8">
          <p className="text-sm text-zinc-400 text-center">{t('fetchError')}</p>
          <button
            onClick={() => { setLoading(true); fetchData() }}
            className="text-xs text-blue-400 hover:text-blue-300 underline"
          >
            {t('retry')}
          </button>
        </div>
      ) : data.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8">
          <p className="text-sm text-zinc-400 text-center">{t('noAssetHistory')}</p>
        </div>
      ) : (
        <AssetChartRecharts data={data} tooltipLabel={t('totalAssetsTooltip')} />
      )}
    </div>
  )
}
