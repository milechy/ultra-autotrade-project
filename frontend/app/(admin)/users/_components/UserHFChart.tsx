'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

interface HFPoint {
  date: string
  hf: number
}

interface UserHFChartProps {
  data: HFPoint[]
}

export function UserHFChart({ data }: UserHFChartProps) {
  const t = useTranslations('AdminUserHFChart')

  if (data.length === 0) {
    return (
      <div className="h-40 flex items-center justify-center text-gray-500 text-sm">
        {t('noData')}
      </div>
    )
  }

  const chartData = data.map((d) => ({
    date: d.date,
    hf: Math.round(d.hf * 100) / 100,
  }))

  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={chartData} margin={{ top: 4, right: 12, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          domain={['auto', 'auto']}
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1f2937',
            border: '1px solid #374151',
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: '#9ca3af' }}
          itemStyle={{ color: '#60a5fa' }}
          formatter={(value: number) => [value.toFixed(2), 'HF']}
        />
        <ReferenceLine y={1.6} stroke="#ef4444" strokeDasharray="4 2" label={{ value: t('dangerLabel'), fill: '#ef4444', fontSize: 10 }} />
        <Line
          type="monotone"
          dataKey="hf"
          stroke="#60a5fa"
          strokeWidth={2}
          dot={{ r: 3, fill: '#60a5fa' }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
