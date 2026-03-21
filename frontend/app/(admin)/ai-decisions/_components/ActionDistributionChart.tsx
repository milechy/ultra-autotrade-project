'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { AiDecision } from '../mock-data'

interface ActionDistributionChartProps {
  decisions: AiDecision[]
}

const PIE_COLORS: Record<string, string> = {
  BUY: '#16a34a',
  SELL: '#dc2626',
  HOLD: '#6b7280',
}

export function ActionDistributionChart({ decisions }: ActionDistributionChartProps) {
  const buyCount = decisions.filter((d) => d.final_action === 'BUY').length
  const sellCount = decisions.filter((d) => d.final_action === 'SELL').length
  const holdCount = decisions.filter((d) => d.final_action === 'HOLD').length

  const pieData = [
    { name: 'BUY', value: buyCount },
    { name: 'SELL', value: sellCount },
    { name: 'HOLD', value: holdCount },
  ].filter((d) => d.value > 0)

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
        BUY/SELL/HOLD分布
      </h3>
      {pieData.length > 0 ? (
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              outerRadius={75}
              dataKey="value"
              label={({ name, percent }) =>
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
              formatter={(value: number, name: string) => [
                `${value}件`,
                name,
              ]}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
          データなし
        </div>
      )}
    </div>
  )
}
