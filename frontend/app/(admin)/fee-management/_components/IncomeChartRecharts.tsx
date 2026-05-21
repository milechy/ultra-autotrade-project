'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

export interface IncomeChartEntry {
  month: string
  subscription: number
  fee: number
  yield_excess: number
}

interface IncomeChartRechartsProps {
  data: IncomeChartEntry[]
}

function yFmt(v: number) {
  if (v >= 1_000_000) return `¥${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `¥${(v / 1_000).toFixed(0)}K`
  return `¥${v}`
}

export function IncomeChartRecharts({ data }: IncomeChartRechartsProps) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
        <XAxis
          dataKey="month"
          tick={{ fontSize: 11, fill: '#71717a' }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tickFormatter={yFmt}
          tick={{ fontSize: 11, fill: '#71717a' }}
          axisLine={false}
          tickLine={false}
          width={52}
        />
        <Tooltip
          formatter={(value: number, name: string) => {
            const labels: Record<string, string> = {
              subscription: 'サブスク',
              fee: '成果報酬',
              yield_excess: '超過利益',
            }
            return [`¥${Math.round(value).toLocaleString()}`, labels[name] ?? name]
          }}
          contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8 }}
          labelStyle={{ color: '#a1a1aa', fontSize: 12 }}
          itemStyle={{ color: '#e4e4e7', fontSize: 12 }}
        />
        <Legend
          formatter={(value: string) => {
            const labels: Record<string, string> = {
              subscription: 'サブスク',
              fee: '成果報酬',
              yield_excess: '超過利益',
            }
            return <span style={{ color: '#a1a1aa', fontSize: 12 }}>{labels[value] ?? value}</span>
          }}
        />
        <Bar dataKey="subscription" stackId="a" fill="#6366f1" radius={[0, 0, 0, 0]} />
        <Bar dataKey="fee" stackId="a" fill="#22c55e" radius={[0, 0, 0, 0]} />
        <Bar dataKey="yield_excess" stackId="a" fill="#f59e0b" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
