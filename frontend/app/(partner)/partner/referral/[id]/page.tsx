'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ChevronLeft, DollarSign, TrendingUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { KPICard } from '@/components/shared/KPICard'
import { getStoredToken } from '@/lib/auth'
import { getReferralTransactions, type ReferralTransaction } from '@/lib/api/referral'
import { getPartnerUserStats, type PartnerUserStats } from '@/lib/api/partner'

const TYPE_LABELS: Record<string, string> = {
  deposit: '入金',
  withdraw: '出金',
  borrow: '借入',
  repay: '返済',
  supply: '供給',
}

function formatType(type: string): string {
  return TYPE_LABELS[type] ?? type
}

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

export default function ReferralUserDetailPage() {
  const params = useParams()
  const userId = Number(params.id)
  const token = getStoredToken()

  const [transactions, setTransactions] = useState<ReferralTransaction[]>([])
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<PartnerUserStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(true)

  const load = useCallback(async () => {
    if (!token || !userId) return
    setLoading(true)
    try {
      const data = await getReferralTransactions(token, userId)
      setTransactions(data)
    } catch {
      setTransactions([])
    } finally {
      setLoading(false)
    }
  }, [token, userId])

  const loadStats = useCallback(async () => {
    if (!token || !userId) return
    setStatsLoading(true)
    try {
      const data = await getPartnerUserStats(token, userId)
      setStats(data)
    } catch {
      setStats(null)
    } finally {
      setStatsLoading(false)
    }
  }, [token, userId])

  useEffect(() => {
    void load()
    void loadStats()
    const id = setInterval(() => {
      void load()
      void loadStats()
    }, 30000)
    return () => clearInterval(id)
  }, [load, loadStats])

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-2">
        <Link
          href="/partner/referral"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          紹介一覧に戻る
        </Link>
      </div>

      <h1 className="text-2xl font-bold">運用状況詳細</h1>

      {/* KPI section */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {statsLoading ? (
          Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))
        ) : (
          <>
            <KPICard
              label="今日の運用総額"
              value={fmtUsd(stats?.today_amount)}
              prefix="$"
              icon={DollarSign}
            />
            <KPICard
              label="今月の利回り"
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
          </>
        )}
      </section>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">取引履歴一覧</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded" />
              ))}
            </div>
          ) : transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">データなし</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">種別</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">金額</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">日時</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx, i) => (
                    <tr key={i} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3">{formatType(tx.type)}</td>
                      <td className="px-4 py-3 text-right font-mono">
                        {Number(tx.amount).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right text-muted-foreground">
                        {new Date(tx.occurred_at).toLocaleDateString('ja-JP', {
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
    </div>
  )
}
