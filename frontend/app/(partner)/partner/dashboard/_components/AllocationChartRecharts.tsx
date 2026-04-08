'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// NOTE: This component must be loaded via dynamic(() => import('./AllocationChartRecharts'), { ssr: false })

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { Allocation } from '@/lib/api/allocations'

const COLORS = [
  '#2563eb', '#16a34a', '#d97706', '#dc2626', '#7c3aed',
  '#0891b2', '#be185d', '#65a30d', '#ea580c', '#6366f1',
]

interface Props {
  allocations: Allocation[]
}

export default function AllocationChartRecharts({ allocations }: Props) {
  if (!allocations || allocations.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
        データがありません
      </div>
    )
  }

  const data = allocations.map((a) => ({
    name: a.tester_name,
    value: Number(a.allocated_amount_usd),
  }))

  return (
    // min-h ensures ResponsiveContainer can measure parent height even in flex/grid layouts
    <div className="min-h-[240px] w-full">
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={80}
            label={({ name, percent }) =>
              `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
            }
            labelLine={false}
          >
            {data.map((_, index) => (
              <Cell key={index} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number) => [
              `$${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)}`,
              '割り当て額',
            ]}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 11 }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
