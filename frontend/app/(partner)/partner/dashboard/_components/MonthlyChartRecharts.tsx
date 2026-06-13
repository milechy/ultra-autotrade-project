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
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { useTranslations } from 'next-intl'

export interface MonthlyData {
  month: string
  start_value: number
  end_value: number
  return_pct: number
  user_count: number
}

interface Props {
  data: MonthlyData[]
}

export default function MonthlyChartRecharts({ data }: Props) {
  const t = useTranslations('PartnerMonthlyChart')

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
        {t('noData')}
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#6b7280' }} />
        <YAxis
          tickFormatter={(v: number) => `${v}%`}
          tick={{ fontSize: 11, fill: '#6b7280' }}
        />
        <ReferenceLine y={0} stroke="#9ca3af" />
        <Tooltip
          formatter={(v: number) => [`${v.toFixed(2)}%`, t('tooltipLabel')]}
          labelStyle={{ fontSize: 12 }}
          contentStyle={{ fontSize: 12 }}
        />
        <Bar dataKey="return_pct" name={t('tooltipLabel')} radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell
              key={index}
              fill={entry.return_pct >= 0 ? '#16a34a' : '#dc2626'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
