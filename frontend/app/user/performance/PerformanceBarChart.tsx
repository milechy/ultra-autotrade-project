'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { useTranslations } from 'next-intl'
import type { MonthlyPnl } from '@/components/transparency'
import { formatJPY } from '@/lib/jpy-converter'

export default function PerformanceBarChart({ monthly }: { monthly: MonthlyPnl[] }) {
  const t = useTranslations('Performance')
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={monthly} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => `¥${(v / 1000).toFixed(0)}k`}
        />
        <Tooltip
          formatter={(v: number) => [formatJPY(v), t('tooltipLabel')]}
          labelFormatter={(l: string) => `${l}${t('monthSuffix')}`}
        />
        <Bar dataKey="gain_jpy" radius={[4, 4, 0, 0]}>
          {monthly.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.gain_jpy >= 0 ? '#16a34a' : '#dc2626'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
