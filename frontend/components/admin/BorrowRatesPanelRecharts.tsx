'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/dashboard/BorrowRatesPanelRecharts.tsx
//
// Recharts を分離 + SSR 無効化用ファイル。
// 親コンポーネント BorrowRatesPanel.tsx から dynamic import される。

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface BorrowRatesChartProps {
  usdcAprPct: number
  ghoVariableAprPct: number
  ghoEffectiveAprPct: number
  /** ラベル（ja.json から渡す） */
  labels: {
    usdc: string
    ghoVariable: string
    ghoEffective: string
    yAxisLabel: string
  }
}

export default function BorrowRatesPanelRecharts({
  usdcAprPct,
  ghoVariableAprPct,
  ghoEffectiveAprPct,
  labels,
}: BorrowRatesChartProps) {
  const data = [
    {
      name: labels.usdc,
      apr: usdcAprPct,
    },
    {
      name: labels.ghoVariable,
      apr: ghoVariableAprPct,
    },
    {
      name: labels.ghoEffective,
      apr: ghoEffectiveAprPct,
    },
  ]

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} />
        <YAxis
          tickFormatter={(v: number) => `${v.toFixed(2)}%`}
          tick={{ fill: '#9ca3af', fontSize: 12 }}
          label={{
            value: labels.yAxisLabel,
            angle: -90,
            position: 'insideLeft',
            fill: '#6b7280',
            fontSize: 11,
          }}
        />
        <Tooltip
          formatter={(value: number) => [`${value.toFixed(4)}%`, 'APR']}
          contentStyle={{ background: '#1f2937', border: '1px solid #374151', color: '#f9fafb' }}
        />
        <Legend wrapperStyle={{ color: '#9ca3af', fontSize: 12 }} />
        <Bar dataKey="apr" fill="#3b82f6" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
