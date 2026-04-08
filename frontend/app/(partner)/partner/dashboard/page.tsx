'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { DollarSign, TrendingUp, Users, Target } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { KPICard } from '@/components/shared/KPICard'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import { fetchAllocations, type Allocation } from '@/lib/api/allocations'
import { getStoredToken } from '@/lib/auth'
import PerformanceSummaryKPI from './_components/PerformanceSummaryKPI'
import AllocationTable from './_components/AllocationTable'
import type { MonthlyData } from './_components/MonthlyChartRecharts'

const MonthlyChart = dynamic(() => import('./_components/MonthlyChartRecharts'), { ssr: false })
const AllocationChart = dynamic(() => import('./_components/AllocationChartRecharts'), { ssr: false })

// ---- Types ----

interface PartnerStats {
  total_aum: number
  yesterday_aum: number
  month_return_pct: number
  yesterday_return_pct: number
  user_count: number
}

interface PartnerUser {
  id: number
  name?: string
  full_name?: string
  email: string
  created_at: string
  aum?: number
  return_pct?: number
  is_active?: boolean
  status?: string
}

interface UsersResponse {
  items?: PartnerUser[]
}

interface AiAccuracy {
  total_decisions: number
  correct_count: number
  accuracy_pct: number
  last_30d_accuracy_pct: number
}

// ---- Helpers ----

function fmtUsd(v: number | undefined): string {
  if (v == null) return '—'
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(v)
}

function fmtPct(v: number | undefined): string {
  if (v == null) return '—'
  return v.toFixed(2)
}

function returnTrend(v: number | undefined): 'up' | 'down' | 'flat' {
  if (v == null || v === 0) return 'flat'
  return v > 0 ? 'up' : 'down'
}

// ---- Page ----

export default function PartnerDashboardPage() {
  const { data: stats, loading: statsLoading } = useAuthFetch<PartnerStats>('/api/partner/stats')
  const { data: usersRaw, loading: usersLoading } = useAuthFetch<UsersResponse | PartnerUser[]>('/users')
  const { data: monthly, loading: monthlyLoading } = useAuthFetch<MonthlyData[]>('/api/partner/monthly')
  const { data: accuracy, loading: accuracyLoading } = useAuthFetch<AiAccuracy>('/ai/accuracy')

  const [allocations, setAllocations] = useState<Allocation[]>([])
  const [allocationsLoading, setAllocationsLoading] = useState(true)

  const loadAllocations = useCallback(async () => {
    const token = getStoredToken()
    if (!token) return
    setAllocationsLoading(true)
    try {
      const items = await fetchAllocations(token)
      setAllocations(items)
    } catch {
      setAllocations([])
    } finally {
      setAllocationsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAllocations()
  }, [loadAllocations])

  // Normalize users response (array or {items: [...]})
  const users: PartnerUser[] = Array.isArray(usersRaw)
    ? usersRaw
    : (usersRaw as UsersResponse)?.items ?? []

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      <h1 className="text-2xl font-bold">パートナーダッシュボード</h1>

      {/* Performance Summary KPI (allocation-based) */}
      <section>
        <PerformanceSummaryKPI />
      </section>

      {/* Allocation Table + Chart */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <AllocationTable />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">割り振り比率</CardTitle>
          </CardHeader>
          <CardContent>
            {allocationsLoading ? (
              <Skeleton className="h-48 rounded-lg" />
            ) : (
              <AllocationChart allocations={allocations} />
            )}
          </CardContent>
        </Card>
      </section>

      {/* KPI Cards */}
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {statsLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))
        ) : (
          <>
            <KPICard
              label="今月の運用金額"
              value={fmtUsd(stats?.total_aum)}
              prefix="$"
              icon={DollarSign}
            />
            <KPICard
              label="昨日の運用金額"
              value={fmtUsd(stats?.yesterday_aum)}
              prefix="$"
              icon={DollarSign}
            />
            <KPICard
              label="今月の利回り"
              value={fmtPct(stats?.month_return_pct)}
              suffix="%"
              trend={returnTrend(stats?.month_return_pct)}
              trendValue={stats?.month_return_pct != null ? `${fmtPct(stats.month_return_pct)}%` : undefined}
              icon={TrendingUp}
            />
            <KPICard
              label="昨日の利回り"
              value={fmtPct(stats?.yesterday_return_pct)}
              suffix="%"
              trend={returnTrend(stats?.yesterday_return_pct)}
              trendValue={stats?.yesterday_return_pct != null ? `${fmtPct(stats.yesterday_return_pct)}%` : undefined}
              icon={TrendingUp}
            />
          </>
        )}
      </section>

      {/* Monthly chart + Accuracy side by side on large screens */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">月別運用実績</CardTitle>
          </CardHeader>
          <CardContent>
            {monthlyLoading ? (
              <Skeleton className="h-48 rounded-lg" />
            ) : (
              <MonthlyChart data={monthly ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="h-4 w-4" />
              AI 的中率
            </CardTitle>
          </CardHeader>
          <CardContent>
            {accuracyLoading ? (
              <Skeleton className="h-32 rounded-lg" />
            ) : accuracy ? (
              <div className="space-y-4">
                <div className="flex flex-col items-center justify-center py-4">
                  <span className="text-4xl font-bold text-blue-600">
                    {accuracy.accuracy_pct.toFixed(1)}%
                  </span>
                  <span className="text-sm text-muted-foreground mt-1">全体的中率</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-muted px-4 py-2">
                  <span className="text-sm text-muted-foreground">直近30日</span>
                  <span className="text-sm font-semibold">
                    {accuracy.last_30d_accuracy_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between px-1">
                  <span className="text-xs text-muted-foreground">
                    総判定数: {accuracy.total_decisions.toLocaleString()} 回
                  </span>
                  <span className="text-xs text-muted-foreground">
                    的中: {accuracy.correct_count.toLocaleString()} 回
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">データなし</p>
            )}
          </CardContent>
        </Card>
      </section>

      {/* User Table */}
      <section>
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Users className="h-4 w-4" />
              配下ユーザー一覧
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {usersLoading ? (
              <div className="p-6 space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 rounded" />
                ))}
              </div>
            ) : users.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">ユーザーがいません</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground">名前</th>
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground">メール</th>
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground">登録日</th>
                      <th className="text-right px-4 py-3 font-medium text-muted-foreground">運用金額</th>
                      <th className="text-right px-4 py-3 font-medium text-muted-foreground">利回り</th>
                      <th className="text-center px-4 py-3 font-medium text-muted-foreground">ステータス</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => {
                      const displayName = u.full_name ?? u.name ?? '—'
                      const active = u.is_active != null ? u.is_active : (u.status === 'active')
                      const returnPct = u.return_pct

                      return (
                        <tr
                          key={u.id}
                          className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                        >
                          <td className="px-4 py-3 font-medium">
                            <Link
                              href={`/partner/users/${u.id}`}
                              className="hover:underline text-foreground"
                            >
                              {displayName}
                            </Link>
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                          <td className="px-4 py-3 text-muted-foreground">
                            {new Date(u.created_at).toLocaleDateString('ja-JP')}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {u.aum != null ? `$${fmtUsd(u.aum)}` : '—'}
                          </td>
                          <td
                            className={`px-4 py-3 text-right font-medium ${
                              returnPct == null
                                ? 'text-muted-foreground'
                                : returnPct >= 0
                                ? 'text-green-600 dark:text-green-400'
                                : 'text-red-600 dark:text-red-400'
                            }`}
                          >
                            {returnPct != null ? `${returnPct.toFixed(2)}%` : '—'}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span
                              className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                                active
                                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                  : 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400'
                              }`}
                            >
                              {active ? 'active' : 'inactive'}
                            </span>
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
      </section>

      {/* Disclaimer */}
      <p className="text-xs text-muted-foreground text-center pb-4">
        ※表示される利回りは参考値であり、将来の収益を保証するものではありません
      </p>
    </div>
  )
}
