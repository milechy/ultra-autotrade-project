'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Dynamic import target for recharts — must NOT be imported directly in page.tsx

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, ReferenceLine,
} from 'recharts'

type TrendPoint = { label: string; score: number; post_count: number }
type CorrelationPoint = { score: number; action: number; label: string }

export function SentimentTrendChart({ data }: { data: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#6b7280' }} interval="preserveStartEnd" />
        <YAxis domain={[-1, 1]} tick={{ fontSize: 11, fill: '#6b7280' }} tickFormatter={(v: number) => v.toFixed(1)} />
        <Tooltip formatter={(v: number) => [v.toFixed(3), 'スコア']} contentStyle={{ fontSize: 12 }} />
        <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 4" />
        <ReferenceLine y={0.2} stroke="#16a34a" strokeDasharray="2 4" strokeOpacity={0.5} />
        <ReferenceLine y={-0.2} stroke="#dc2626" strokeDasharray="2 4" strokeOpacity={0.5} />
        <Line type="monotone" dataKey="score" stroke="#2563eb" strokeWidth={2} dot={false} name="センチメントスコア" />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function SentimentCorrelationChart({ data }: { data: CorrelationPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="score" type="number" domain={[-1, 1]} name="センチメントスコア" tick={{ fontSize: 11 }} tickFormatter={(v: number) => v.toFixed(1)} />
        <YAxis dataKey="action" type="number" domain={[-1.5, 1.5]} name="AI判定" tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => v === 1 ? 'BUY' : v === -1 ? 'SELL' : 'HOLD'} />
        <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ fontSize: 12 }}
          formatter={(v: number, name: string) => {
            if (name === 'AI判定') return [v === 1 ? 'BUY' : v === -1 ? 'SELL' : 'HOLD', name]
            return [typeof v === 'number' ? v.toFixed(3) : v, name]
          }} />
        <Scatter data={data} fill="#2563eb" opacity={0.6} />
      </ScatterChart>
    </ResponsiveContainer>
  )
}
