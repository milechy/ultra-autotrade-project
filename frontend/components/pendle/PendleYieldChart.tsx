'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// NOTE: This component must be loaded via:
//   dynamic(() => import('./PendleYieldChart'), { ssr: false })
// to prevent SSR crash (recharts は SSR 非対応)

import { useTranslations } from 'next-intl'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { PendleApyPoint } from '@/lib/api/pendle'

interface Props {
  data: PendleApyPoint[]
  /** グラフタイトル（オプション） */
  title?: string
}

/** APY 点 1件ぶんのチャート用データ */
interface ChartPoint {
  /** 表示用日付 (MM/DD 形式) */
  date: string
  /** APY 値 (Number 変換済み) */
  apy: number
}

function formatDate(isoDate: string): string {
  // YYYY-MM-DD → MM/DD
  const parts = isoDate.split('-')
  if (parts.length >= 3) {
    return `${parts[1]}/${parts[2]}`
  }
  return isoDate
}

export default function PendleYieldChart({ data, title }: Props) {
  const t = useTranslations("PendleYieldChart")
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-zinc-500">
        {t("noData")}
      </div>
    )
  }

  const chartData: ChartPoint[] = data.map((point) => ({
    date: formatDate(point.date),
    // Decimal 型文字列 → Number 変換 (CLAUDE.md 標準チェックリスト準拠)
    apy: Number(point.apy),
  }))

  return (
    <div className="w-full">
      {title && (
        <p className="text-xs text-zinc-400 mb-2 font-medium">{title}</p>
      )}
      {/* min-h で ResponsiveContainer の高さ計測を保証 */}
      <div className="min-h-[180px] w-full">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#a1a1aa' }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#a1a1aa' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
              width={48}
            />
            <Tooltip
              contentStyle={{
                background: '#18181b',
                border: '1px solid #3f3f46',
                borderRadius: 6,
                fontSize: 12,
              }}
              labelStyle={{ color: '#a1a1aa' }}
              formatter={(value: number) => [`${value.toFixed(2)}%`, 'APY']}
            />
            <Line
              type="monotone"
              dataKey="apy"
              stroke="#6366f1"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#6366f1' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
