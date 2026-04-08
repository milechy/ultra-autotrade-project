'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { DollarSign, TrendingUp, Users, Shield } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { fetchPerformance, type PerformanceResponse } from '@/lib/api/allocations'
import { getStoredToken } from '@/lib/auth'

function fmtUsd(v: number): string {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(v)
}

function fmtPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

function pnlColor(v: number): string {
  if (v > 0) return 'text-green-600 dark:text-green-400'
  if (v < 0) return 'text-red-600 dark:text-red-400'
  return 'text-muted-foreground'
}

function hfColor(hf: number | null): string {
  if (hf === null) return 'text-muted-foreground'
  if (hf > 1.8) return 'text-green-600 dark:text-green-400'
  if (hf >= 1.6) return 'text-yellow-500 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}

export default function PerformanceSummaryKPI() {
  const [data, setData] = useState<PerformanceResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = getStoredToken()
    if (!token) return

    setLoading(true)
    fetchPerformance(token)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    )
  }

  const s = data?.summary

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {/* 運用総額 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">運用総額</CardTitle>
          <DollarSign className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {s != null ? `$${fmtUsd(s.total_aum_usd)}` : '—'}
          </div>
        </CardContent>
      </Card>

      {/* 全体損益 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">全体損益</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {s != null ? (
            <>
              <div className={`text-2xl font-bold ${pnlColor(s.total_pnl_usd)}`}>
                {s.total_pnl_usd >= 0 ? '+' : ''}${fmtUsd(Math.abs(s.total_pnl_usd))}
              </div>
              <div className={`text-xs mt-1 ${pnlColor(s.total_pnl_percentage)}`}>
                {fmtPct(s.total_pnl_percentage)}
              </div>
            </>
          ) : (
            <div className="text-2xl font-bold">—</div>
          )}
        </CardContent>
      </Card>

      {/* テスター数 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">テスター数</CardTitle>
          <Users className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {s != null ? s.tester_count : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">人</div>
        </CardContent>
      </Card>

      {/* Health Factor */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Health Factor</CardTitle>
          <Shield className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${hfColor(s?.health_factor ?? null)}`}>
            {s?.health_factor != null ? s.health_factor.toFixed(2) : '—'}
          </div>
          {s?.health_factor != null && (
            <div className={`text-xs mt-1 ${hfColor(s.health_factor)}`}>
              {s.health_factor > 1.8 ? '安全' : s.health_factor >= 1.6 ? '注意' : '危険'}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
