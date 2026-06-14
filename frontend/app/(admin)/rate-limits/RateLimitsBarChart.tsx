'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Dynamic import target for recharts — must NOT be imported directly in page.tsx

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { useTranslations } from 'next-intl'

type ChartEntry = {
  name: string
  usage_pct: number
  current: number
  limit: number
}

function usageColor(pct: number): string {
  if (pct >= 90) return '#dc2626'
  if (pct >= 80) return '#ca8a04'
  return '#16a34a'
}

export default function RateLimitsBarChart({ data }: { data: ChartEntry[] }) {
  const t = useTranslations('AdminRateLimitsChart')
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 40 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#6b7280' }} angle={-20} textAnchor="end" interval={0} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#6b7280' }} tickFormatter={(v: number) => `${v}%`} />
        <Tooltip
          formatter={(v: number) => [`${v.toFixed(1)}%`, t('usageRate')]}
          contentStyle={{ fontSize: 12 }}
        />
        <Bar dataKey="usage_pct" name={t('usageRate')} radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={usageColor(entry.usage_pct)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
