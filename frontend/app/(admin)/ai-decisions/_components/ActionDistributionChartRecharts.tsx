'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// recharts を直接使う実装。ActionDistributionChart から dynamic() で読み込む。

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

export interface PieEntry {
  name: string
  value: number
}

interface ActionDistributionChartRechartsProps {
  pieData: PieEntry[]
}

const PIE_COLORS: Record<string, string> = {
  BUY: '#16a34a',
  SELL: '#dc2626',
  HOLD: '#6b7280',
}

export function ActionDistributionChartRecharts({
  pieData,
}: ActionDistributionChartRechartsProps) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={pieData}
          cx="50%"
          cy="50%"
          outerRadius={75}
          dataKey="value"
          label={({ name, percent }: { name: string; percent: number }) =>
            `${name} ${(percent * 100).toFixed(0)}%`
          }
          labelLine={false}
        >
          {pieData.map((entry) => (
            <Cell
              key={entry.name}
              fill={PIE_COLORS[entry.name] ?? '#9ca3af'}
            />
          ))}
        </Pie>
        <Tooltip
          formatter={(value: number, name: string) => [`${value}件`, name]}
        />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}
