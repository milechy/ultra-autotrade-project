'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useMemo } from 'react'
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

interface DataPoint {
  date: string
  value: number
}

// TODO: Replace with GET /api/portfolio/history?period=Xd when backend endpoint is ready
function generateMockData(days: number): DataPoint[] {
  const result: DataPoint[] = []
  let value = 7500
  const now = new Date()
  for (let i = days; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    value += (Math.random() - 0.45) * 80
    value = Math.max(6000, value)
    result.push({
      date: d.toLocaleDateString('ja-JP', { month: 'short', day: 'numeric' }),
      value: Math.round(value),
    })
  }
  return result
}

function formatYAxis(v: number) {
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`
  return `$${v}`
}

export function AssetChart() {
  const [days, setDays] = useState(30)

  const data = useMemo(() => generateMockData(days), [days])

  const handleRangeChange = (range: { from: Date; to: Date } | 'all') => {
    if (range === 'all') {
      setDays(365)
    } else {
      const ms = range.to.getTime() - range.from.getTime()
      setDays(Math.round(ms / 86_400_000))
    }
  }

  return (
    <div className="space-y-3">
      <DateRangeFilter onChange={handleRangeChange} presets />
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
    </div>
  )
}
