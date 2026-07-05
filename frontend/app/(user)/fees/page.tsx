// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api/client'
import { useAuth } from '@/lib/auth'
import AuthGuard from '@/components/AuthGuard'
import FeePlanSection from '@/components/user/FeePlanSection'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FeeSummary {
  user_id: number
  total_fee_paid_jpy: string
  total_subscription_paid_jpy: string
  total_user_takehome_jpy: string
  total_yield_excess_to_uata_jpy: string
  months_count: number
}

interface FeeHistoryItem {
  calculation_month: string
  tier: string
  risk_mode: string
  deposit_jpy: string
  net_profit_jpy: string
  fee_amount_jpy: string
  subscription_amount_jpy: string
  user_takehome_jpy: string
  finalized_at: string | null
}

type FeeHistoryResponse = FeeHistoryItem[]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TIER_LABELS: Record<string, string> = {
  LOWER: 'スタンダード',
  MIDDLE: 'プレミアム',
  UPPER: 'アルティメット',
  GENERAL: 'スタンダード',
}

const RISK_LABELS: Record<string, string> = {
  conservative: '保守的',
  balanced: 'バランス',
  aggressive: '積極的',
}

function jpyFmt(v: string | number) {
  const n = typeof v === 'string' ? Number(v) : v
  return `¥${Math.round(n).toLocaleString()}`
}

function monthFmt(s: string) {
  const d = new Date(s)
  return `${d.getFullYear()}年${d.getMonth() + 1}月`
}

// ---------------------------------------------------------------------------
// Summary card
// ---------------------------------------------------------------------------

function SummarySection({ summary }: { summary: FeeSummary }) {
  const cards = [
    { label: '累計手数料', value: jpyFmt(summary.total_fee_paid_jpy) },
    { label: '累計サブスク', value: jpyFmt(summary.total_subscription_paid_jpy) },
    { label: '累計手取り', value: jpyFmt(summary.total_user_takehome_jpy) },
    { label: '記録月数', value: `${summary.months_count} ヶ月` },
  ]
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map(({ label, value }) => (
        <Card key={label} className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-zinc-500 mb-1">{label}</p>
            <p className="text-base font-semibold text-zinc-100">{value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// History table
// ---------------------------------------------------------------------------

function HistoryTable({ items }: { items: FeeHistoryItem[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-zinc-500 text-center py-8">
        手数料履歴がありません
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
            <th className="text-left py-2 pr-3">対象月</th>
            <th className="text-left py-2 pr-3">Tier</th>
            <th className="text-right py-2 pr-3">運用益</th>
            <th className="text-right py-2 pr-3">手数料</th>
            <th className="text-right py-2 pr-3">サブスク</th>
            <th className="text-right py-2">手取り</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.calculation_month}
              className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
            >
              <td className="py-2.5 pr-3 text-zinc-100">{monthFmt(item.calculation_month)}</td>
              <td className="py-2.5 pr-3 text-zinc-400">
                {TIER_LABELS[item.tier] ?? item.tier}
              </td>
              <td className="py-2.5 pr-3 text-right text-zinc-300">
                {jpyFmt(item.net_profit_jpy)}
              </td>
              <td className="py-2.5 pr-3 text-right text-zinc-300">
                {jpyFmt(item.fee_amount_jpy)}
              </td>
              <td className="py-2.5 pr-3 text-right text-zinc-300">
                {jpyFmt(item.subscription_amount_jpy)}
              </td>
              <td className="py-2.5 text-right text-emerald-400 font-medium">
                {jpyFmt(item.user_takehome_jpy)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function FeesContent() {
  const { token } = useAuth()
  const [summary, setSummary] = useState<FeeSummary | null>(null)
  const [history, setHistory] = useState<FeeHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    const fetchAll = async () => {
      try {
        const [sumRes, histRes] = await Promise.all([
          apiFetch<FeeSummary>('/api/v1/fees/my-summary'),
          apiFetch<FeeHistoryResponse>('/api/v1/fees/my-history?limit=24'),
        ])
        setSummary(sumRes)
        setHistory(histRes)
      } catch {
        setError('データの取得に失敗しました')
      } finally {
        setLoading(false)
      }
    }
    void fetchAll()
  }, [token])

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* ヘッダー */}
      <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="px-4 py-3">
          <h1 className="text-lg font-semibold text-zinc-100">手数料・実績</h1>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4 pb-24 max-w-4xl mx-auto">
        {/* B-1: 料金プラン / Tier別月額の事前提示（config は独自に取得・独立描画） */}
        {/* B-3: 決済手段（自動引き落とし）設定への導線もここから提示 */}
        <FeePlanSection showPaymentLink />

        {loading && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 rounded-xl bg-zinc-800" />
              ))}
            </div>
            <Skeleton className="h-40 rounded-xl bg-zinc-800" />
          </div>
        )}

        {error && !loading && (
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="pt-4">
              <p className="text-sm text-red-400">{error}</p>
            </CardContent>
          </Card>
        )}

        {!loading && !error && (
          <>
            {summary && <SummarySection summary={summary} />}

            <Card className="bg-zinc-900 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-100">月次手数料履歴</CardTitle>
              </CardHeader>
              <CardContent>
                <HistoryTable items={history} />
              </CardContent>
            </Card>

            <p className="text-xs text-zinc-600 text-center">
              * 手数料は月末に確定します。表示は概算の場合があります。
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export default function FeesPage() {
  return (
    <AuthGuard>
      <FeesContent />
    </AuthGuard>
  )
}
