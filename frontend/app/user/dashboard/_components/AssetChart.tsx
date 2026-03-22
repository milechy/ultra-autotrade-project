'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useCallback } from 'react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import { DateRangeFilter } from '@/components/shared'
import { Skeleton } from '@/components/ui/skeleton'
import { apiFetch } from '@/lib/api/client'

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

function formatYAxis(v: number) {
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`
  return `$${v}`
}

export function AssetChart() {
  const [period, setPeriod] = useState<string>('30d')
  const [data, setData] = useState<DataPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchData = useCallback(async () => {
    setError(false)
    try {
      const res = await apiFetch<PortfolioHistoryResponse>(
        `/api/portfolio/history?period=${period}&interval=daily`,
      )
      const mapped: DataPoint[] = res.items.map((item) => ({
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
  }, [period])

  useEffect(() => {
    setLoading(true)
    fetchData()
  }, [fetchData])

  // 30-second auto-refresh
  useEffect(() => {
    const id = setInterval(() => fetchData(), 30_000)
    return () => clearInterval(id)
  }, [fetchData])

  const handleRangeChange = (range: { from: Date; to: Date } | 'all') => {
    if (range === 'all') {
      setPeriod('all')
    } else {
      const days = Math.round(
        (range.to.getTime() - range.from.getTime()) / 86_400_000,
      )
      if (days <= 7) {
        setPeriod('7d')
      } else if (days <= 30) {
        setPeriod('30d')
      } else {
        setPeriod('90d')
      }
    }
  }

  return (
    <div className="space-y-3">
      <DateRangeFilter onChange={handleRangeChange} presets />
      {loading ? (
        <Skeleton className="h-[200px] rounded-xl" />
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-8">
          <p className="text-sm text-zinc-400 text-center">データを取得できません</p>
          <button
            onClick={() => { setLoading(true); fetchData() }}
            className="text-xs text-blue-400 hover:text-blue-300 underline"
          >
            再試行
          </button>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#71717a' }}
              interval="preserveStartEnd"
              tickLine={false}
            />
            <YAxis
              tickFormatter={formatYAxis}
              tick={{ fontSize: 10, fill: '#71717a' }}
              tickLine={false}
              axisLine={false}
              width={52}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#18181b',
                border: '1px solid #3f3f46',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              formatter={(v: number) => [`$${v.toLocaleString()}`, '総資産']}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#60a5fa"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#60a5fa' }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
