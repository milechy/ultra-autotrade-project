'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// NOTE: This component must be loaded via dynamic(() => import('./PnlChartRecharts'), { ssr: false })

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts'

interface PnlPoint {
  date: string
  pnl: number
}

function formatYAxis(v: number) {
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`
  return `$${v}`
}

export default function PnlChartRecharts({ data, tooltipLabel }: { data: PnlPoint[]; tooltipLabel?: string }) {
  const allPositive = data.every((d) => d.pnl >= 0)
  const allNegative = data.every((d) => d.pnl <= 0)
  const lineColor = allNegative ? '#f87171' : allPositive ? '#34d399' : '#60a5fa'

  return (
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
          width={56}
        />
        <ReferenceLine y={0} stroke="#71717a" strokeDasharray="4 2" />
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: '8px',
            fontSize: '12px',
          }}
          formatter={(v: number) => {
            const sign = v >= 0 ? '+' : ''
            return [`${sign}$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, tooltipLabel ?? '']
          }}
        />
        <Line
          type="monotone"
          dataKey="pnl"
          stroke={lineColor}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: lineColor }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
