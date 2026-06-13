'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ChevronLeft, DollarSign, TrendingUp } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { KPICard } from '@/components/shared/KPICard'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import type { PartnerUserStats } from '@/lib/api/partner'
import type { AIDecisionAPIResponse } from '@/lib/api/ai-decisions'

// ---- Types ----

interface DecisionListResponse {
  items: AIDecisionAPIResponse[]
  total: number
}

// ---- Helpers ----

function fmtUsd(v: string | null | undefined): string {
  if (v == null) return '—'
  const n = Number(v)
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n)
}

function fmtPct(v: string | null | undefined): string {
  if (v == null) return '—'
  return Number(v).toFixed(2)
}

function returnTrend(v: string | null | undefined): 'up' | 'down' | 'flat' {
  if (v == null) return 'flat'
  const n = Number(v)
  if (n > 0) return 'up'
  if (n < 0) return 'down'
  return 'flat'
}

const ACTION_COLORS: Record<string, string> = {
  BUY: 'text-green-600 dark:text-green-400',
  SELL: 'text-red-600 dark:text-red-400',
  HOLD: 'text-yellow-600 dark:text-yellow-400',
}

// ---- Page ----

export default function PartnerUserDetailPage() {
  const t = useTranslations('PartnerUserDetail')
  const params = useParams()
  const userId = Number(params.id)

  const { data: stats, loading: statsLoading } = useAuthFetch<PartnerUserStats>(
    userId ? `/api/partner/users/${userId}/stats` : null,
    { refreshInterval: 30000 },
  )

  const { data: decisions, loading: decisionsLoading } = useAuthFetch<DecisionListResponse>(
    '/api/ai/decisions?limit=5&offset=0',
    { refreshInterval: 30000 },
  )

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      <div className="flex items-center gap-2">
        <Link
          href="/partner/users"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          {t('backToList')}
        </Link>
      </div>

      <h1 className="text-2xl font-bold">{t('pageTitle')}</h1>

      {/* KPI Cards */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {statsLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))
        ) : (
          <>
            <KPICard
              label={t('kpiTodayBalance')}
              value={fmtUsd(stats?.today_amount)}
              prefix="$"
              icon={DollarSign}
            />
            <KPICard
              label={t('kpiMonthReturn')}
              value={fmtPct(stats?.month_return_pct)}
              suffix="%"
              trend={returnTrend(stats?.month_return_pct)}
              trendValue={
                stats?.month_return_pct != null
                  ? `${fmtPct(stats.month_return_pct)}%`
                  : undefined
              }
              icon={TrendingUp}
            />
            <KPICard
              label={t('kpiYesterdayReturn')}
              value={fmtPct(stats?.yesterday_return_pct)}
              suffix="%"
              trend={returnTrend(stats?.yesterday_return_pct)}
              trendValue={
                stats?.yesterday_return_pct != null
                  ? `${fmtPct(stats.yesterday_return_pct)}%`
                  : undefined
              }
              icon={TrendingUp}
            />
          </>
        )}
      </section>

      {/* AI判定 (latest 5 system decisions) */}
      <section>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('aiHistoryTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {decisionsLoading ? (
              <div className="p-6 space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 rounded" />
                ))}
              </div>
            ) : !decisions || decisions.items.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">{t('noData')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground">
                        {t('colDecision')}
                      </th>
                      <th className="text-right px-4 py-3 font-medium text-muted-foreground">
                        {t('colConfidence')}
                      </th>
                      <th className="text-right px-4 py-3 font-medium text-muted-foreground">
                        {t('colDate')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.items.map((d) => (
                      <tr
                        key={d.id}
                        className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                      >
                        <td
                          className={`px-4 py-3 font-semibold ${ACTION_COLORS[d.action] ?? ''}`}
                        >
                          {d.action}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {Number(d.confidence).toFixed(1)}%
                        </td>
                        <td className="px-4 py-3 text-right text-muted-foreground">
                          {new Date(d.created_at).toLocaleDateString('ja-JP', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <p className="text-xs text-muted-foreground text-center pb-4">
        {t('disclaimer')}
      </p>
    </div>
  )
}
