'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// recharts を直接使う実装。AILearningCharts から dynamic() で読み込む。

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

// ──────────────────────────────────────────────────────────────────────────────
// フィードバック件数バーチャート
// ──────────────────────────────────────────────────────────────────────────────

export interface FeedbackCountData {
  name: string
  件数: number
}

interface FeedbackBarChartProps {
  data: FeedbackCountData[]
}

const BAR_COLORS = ['#6366f1', '#16a34a', '#dc2626']

export function FeedbackBarChart({ data }: FeedbackBarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
        <Tooltip
          formatter={(value: number, name: string) => [`${value}件`, name]}
        />
        <Bar dataKey="件数">
          {data.map((_, index) => (
            <Cell key={index} fill={BAR_COLORS[index % BAR_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ──────────────────────────────────────────────────────────────────────────────
// フィードバックソース円グラフ
// ──────────────────────────────────────────────────────────────────────────────

export interface SourcePieEntry {
  name: string
  value: number
}

interface SourcePieChartProps {
  data: SourcePieEntry[]
}

const SOURCE_LABELS: Record<string, string> = {
  manual: '手動',
  auto_howl: '自動(HOWL)',
  auto_outcome: '自動(実績)',
}

const PIE_COLORS = ['#6366f1', '#16a34a', '#f59e0b', '#6b7280']

export function SourcePieChart({ data }: SourcePieChartProps) {
  const labeled = data.map((d) => ({
    ...d,
    name: SOURCE_LABELS[d.name] ?? d.name,
  }))
  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={labeled}
          cx="50%"
          cy="50%"
          outerRadius={70}
          dataKey="value"
          label={({ name, percent }: { name: string; percent: number }) =>
            `${name} ${(percent * 100).toFixed(0)}%`
          }
          labelLine={false}
        >
          {labeled.map((_, index) => (
            <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
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
