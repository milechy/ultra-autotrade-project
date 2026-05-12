'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  fetchAllocations,
  type Allocation,
  type TesterPerformance,
} from '@/lib/api/allocations'
import { getStoredToken } from '@/lib/auth'

interface Props {
  /** tester_name → TesterPerformance from /api/partner/performance */
  performanceMap?: Record<string, TesterPerformance>
  /** user_id → tier ("LOWER" | "MIDDLE" | "UPPER", v9 互換: "GENERAL") */
  tierMap?: Record<number, string>
}

function pnlColor(v: number): string {
  if (v > 0) return 'text-green-600 dark:text-green-400'
  if (v < 0) return 'text-red-600 dark:text-red-400'
  return 'text-gray-600 dark:text-gray-400'
}

function fmtUsd(v: number): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)
}

// Tier ラベル辞書 (backend TIER_JP_LABELS と整合 — app/auth/models.py)
// GENERAL は v9 互換 (LOWER と同義、F-13 で削除予定)
const TIER_LABELS: Record<string, string> = {
  LOWER: '一般',
  MIDDLE: 'ミドル',
  UPPER: 'アッパー',
  GENERAL: '一般',
}

function tierBadgeClass(tier: string): string {
  if (tier === 'UPPER') {
    return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
  }
  if (tier === 'MIDDLE') {
    return 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400'
  }
  return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
}

function TierBadge({ tier }: { tier?: string }) {
  if (!tier) return <span className="text-muted-foreground text-xs">—</span>
  const label = TIER_LABELS[tier] ?? tier
  return (
    <span
      data-testid={`tier-badge-${tier}`}
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tierBadgeClass(tier)}`}
    >
      {label}
    </span>
  )
}

export default function AllocationTable({ performanceMap = {}, tierMap = {} }: Props) {
  const [allocations, setAllocations] = useState<Allocation[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    const token = getStoredToken()
    if (!token) return
    setLoading(true)
    try {
      const items = await fetchAllocations(token)
      setAllocations(items)
    } catch {
      setAllocations([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">資金割り振り一覧</CardTitle>
        <span className="inline-block rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
          閲覧のみ（廃止予定）
        </span>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-6 space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 rounded" />
            ))}
          </div>
        ) : allocations.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            割り振りデータがありません
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">名前</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">元本 (USD)</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">現在値 (USD)</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">損益 (USD)</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">利回り</th>
                  <th className="text-center px-4 py-3 font-medium text-muted-foreground">ティア</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">割当日</th>
                </tr>
              </thead>
              <tbody>
                {allocations.map((item) => {
                  const perf = performanceMap[item.tester_name]
                  const tier = perf?.user_id != null ? tierMap[perf.user_id] : undefined
                  return (
                    <tr
                      key={item.id}
                      className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium">{item.tester_name}</td>
                      <td className="px-4 py-3 text-right">${fmtUsd(Number(item.allocated_amount_usd))}</td>
                      <td className="px-4 py-3 text-right">
                        {perf?.current_value_usd != null ? `$${fmtUsd(Number(perf.current_value_usd))}` : '—'}
                      </td>
                      <td className={`px-4 py-3 text-right font-medium ${perf?.pnl_usd != null ? pnlColor(Number(perf.pnl_usd)) : 'text-muted-foreground'}`}>
                        {perf?.pnl_usd != null
                          ? `${Number(perf.pnl_usd) >= 0 ? '+' : ''}$${fmtUsd(Math.abs(Number(perf.pnl_usd)))}`
                          : '—'}
                      </td>
                      <td className={`px-4 py-3 text-right font-medium ${perf?.pnl_percentage != null ? pnlColor(Number(perf.pnl_percentage)) : 'text-muted-foreground'}`}>
                        {perf?.pnl_percentage != null
                          ? `${Number(perf.pnl_percentage) >= 0 ? '+' : ''}${Number(perf.pnl_percentage).toFixed(2)}%`
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <TierBadge tier={tier} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(item.allocated_at).toLocaleDateString('ja-JP')}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
