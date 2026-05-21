// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import dynamic from 'next/dynamic'
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '@/lib/api/client'
import { useAuth } from '@/lib/auth'
import AuthGuard from '@/components/AuthGuard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { IncomeChartEntry } from './_components/IncomeChartRecharts'

const IncomeChartRecharts = dynamic(
  () =>
    import('./_components/IncomeChartRecharts').then((m) => ({
      default: m.IncomeChartRecharts,
    })),
  { ssr: false },
)

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AllUsersFeeItem {
  user_id: number
  calculation_month: string
  tier: string
  risk_mode: string
  deposit_jpy: string
  net_profit_jpy: string
  fee_amount_jpy: string
  subscription_amount_jpy: string
  user_takehome_jpy: string
  affiliate_id: number | null
  affiliate_amount_jpy: string
  finalized_at: string | null
}

interface UataIncomeResponse {
  month_from: string
  month_to: string
  subscription_total: string
  fee_total: string
  yield_excess_total: string
  affiliate_payout_total: string
  uata_income_total: string
}

interface FinalizeResult {
  calculation_month: string
  dry_run: boolean
  users_processed: number
  users_skipped_no_snapshot: number
  users_skipped_already_finalized: number
  total_fee_jpy: string
  total_subscription_jpy: string
  total_user_takehome_jpy: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TIER_LABELS: Record<string, string> = {
  LOWER: 'スタンダード',
  MIDDLE: 'プレミアム',
  UPPER: 'アルティメット',
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

function todayMonthStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

function buildMonthOptions() {
  const options: { value: string; label: string }[] = []
  const now = new Date()
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
    options.push({ value, label: `${d.getFullYear()}年${d.getMonth() + 1}月` })
  }
  return options
}

// ---------------------------------------------------------------------------
// ユーザー別手数料テーブル
// ---------------------------------------------------------------------------

function UsersTable({
  items,
  onFinalize,
}: {
  items: AllUsersFeeItem[]
  onFinalize: () => void
}) {
  const [sortKey, setSortKey] = useState<keyof AllUsersFeeItem>('user_id')
  const [sortAsc, setSortAsc] = useState(true)

  const sorted = [...items].sort((a, b) => {
    const av = a[sortKey]
    const bv = b[sortKey]
    if (av === null) return 1
    if (bv === null) return -1
    const cmp = String(av) < String(bv) ? -1 : String(av) > String(bv) ? 1 : 0
    return sortAsc ? cmp : -cmp
  })

  function thBtn(label: string, key: keyof AllUsersFeeItem) {
    const active = sortKey === key
    return (
      <button
        onClick={() => {
          if (active) setSortAsc((v) => !v)
          else { setSortKey(key); setSortAsc(true) }
        }}
        className={`text-xs text-left whitespace-nowrap py-2 pr-3 font-medium ${active ? 'text-zinc-200' : 'text-zinc-500'} hover:text-zinc-300`}
      >
        {label}{active ? (sortAsc ? ' ▲' : ' ▼') : ''}
      </button>
    )
  }

  if (items.length === 0) {
    return (
      <p className="text-sm text-zinc-500 text-center py-8">
        対象月のデータがありません
      </p>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-zinc-500">{items.length} 件</p>
        <Button size="sm" variant="outline" onClick={onFinalize} className="text-xs h-7">
          月次 finalize 実行
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left">{thBtn('UID', 'user_id')}</th>
              <th className="text-left">{thBtn('Tier', 'tier')}</th>
              <th className="text-left">{thBtn('リスク', 'risk_mode')}</th>
              <th className="text-right">{thBtn('入金', 'deposit_jpy')}</th>
              <th className="text-right">{thBtn('純利益', 'net_profit_jpy')}</th>
              <th className="text-right">{thBtn('手数料', 'fee_amount_jpy')}</th>
              <th className="text-right">{thBtn('サブスク', 'subscription_amount_jpy')}</th>
              <th className="text-right">{thBtn('手取り', 'user_takehome_jpy')}</th>
              <th className="text-left text-xs text-zinc-500 py-2">確定</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((item) => (
              <tr
                key={item.user_id}
                className="border-b border-zinc-800/40 hover:bg-zinc-800/20"
              >
                <td className="py-2.5 pr-3 text-zinc-300">{item.user_id}</td>
                <td className="py-2.5 pr-3 text-zinc-400 text-xs">{TIER_LABELS[item.tier] ?? item.tier}</td>
                <td className="py-2.5 pr-3 text-zinc-400 text-xs">{RISK_LABELS[item.risk_mode] ?? item.risk_mode}</td>
                <td className="py-2.5 pr-3 text-right text-zinc-400">{jpyFmt(item.deposit_jpy)}</td>
                <td className={`py-2.5 pr-3 text-right ${Number(item.net_profit_jpy) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {jpyFmt(item.net_profit_jpy)}
                </td>
                <td className="py-2.5 pr-3 text-right text-zinc-300">{jpyFmt(item.fee_amount_jpy)}</td>
                <td className="py-2.5 pr-3 text-right text-zinc-300">{jpyFmt(item.subscription_amount_jpy)}</td>
                <td className="py-2.5 pr-3 text-right text-zinc-100 font-medium">{jpyFmt(item.user_takehome_jpy)}</td>
                <td className="py-2.5 text-xs">
                  {item.finalized_at ? (
                    <span className="text-emerald-500">確定済</span>
                  ) : (
                    <span className="text-zinc-600">未確定</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Finalize モーダル
// ---------------------------------------------------------------------------

function FinalizeModal({
  month,
  token,
  onClose,
}: {
  month: string
  token: string
  onClose: () => void
}) {
  const [dryRun, setDryRun] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<FinalizeResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ month, dry_run: String(dryRun) })
      const res = await apiFetch<FinalizeResult>(
        `/api/v1/fees/finalize-month?${params.toString()}`,
        { method: 'POST' },
      )
      setResult(res)
    } catch {
      setError('実行に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-sm mx-4">
        <h3 className="text-base font-semibold text-zinc-100 mb-4">月次 finalize 実行</h3>

        {!result && (
          <>
            <p className="text-sm text-zinc-400 mb-4">
              対象月: <span className="text-zinc-200">{monthFmt(month)}</span>
            </p>
            <label className="flex items-center gap-2 text-sm text-zinc-300 mb-5 cursor-pointer">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                className="accent-indigo-500"
              />
              dry_run（DB 書込なし・計算のみ）
            </label>
            {error && <p className="text-xs text-red-400 mb-3">{error}</p>}
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={onClose} className="flex-1">キャンセル</Button>
              <Button
                size="sm"
                onClick={run}
                disabled={loading}
                className={`flex-1 ${dryRun ? 'bg-zinc-700 hover:bg-zinc-600' : 'bg-indigo-600 hover:bg-indigo-700'}`}
              >
                {loading ? '実行中…' : dryRun ? 'dry_run 実行' : '本番実行'}
              </Button>
            </div>
          </>
        )}

        {result && (
          <>
            <div className="space-y-2 mb-5 text-sm">
              {result.dry_run && (
                <p className="text-amber-400 text-xs font-medium">dry_run モード（DB 未書込）</p>
              )}
              <div className="grid grid-cols-2 gap-1 text-xs">
                <span className="text-zinc-500">処理ユーザー</span>
                <span className="text-zinc-200 text-right">{result.users_processed} 名</span>
                <span className="text-zinc-500">スキップ（スナップなし）</span>
                <span className="text-zinc-400 text-right">{result.users_skipped_no_snapshot} 名</span>
                <span className="text-zinc-500">スキップ（確定済）</span>
                <span className="text-zinc-400 text-right">{result.users_skipped_already_finalized} 名</span>
                <span className="text-zinc-500">手数料合計</span>
                <span className="text-zinc-200 text-right">{jpyFmt(result.total_fee_jpy)}</span>
                <span className="text-zinc-500">サブスク合計</span>
                <span className="text-zinc-200 text-right">{jpyFmt(result.total_subscription_jpy)}</span>
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={onClose} className="w-full">閉じる</Button>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// UATa 収益セクション
// ---------------------------------------------------------------------------

function IncomeSection({ token }: { token: string }) {
  const now = new Date()
  const defaultFrom = `${now.getFullYear()}-01-01`
  const defaultTo = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`

  const [monthFrom, setMonthFrom] = useState(defaultFrom)
  const [monthTo, setMonthTo] = useState(defaultTo)
  const [income, setIncome] = useState<UataIncomeResponse | null>(null)
  const [chartData, setChartData] = useState<IncomeChartEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchIncome = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ month_from: monthFrom, month_to: monthTo })
      const data = await apiFetch<UataIncomeResponse>(`/api/v1/fees/uata-income?${params.toString()}`)
      setIncome(data)
      // 月別チャート用（現在APIは集計値のみなので1本表示）
      const entry: IncomeChartEntry = {
        month: `${new Date(monthFrom).getFullYear()}/${new Date(monthFrom).getMonth() + 1}〜`,
        subscription: Number(data.subscription_total),
        fee: Number(data.fee_total),
        yield_excess: Number(data.yield_excess_total),
      }
      setChartData([entry])
    } catch {
      setError('データ取得に失敗しました')
    } finally {
      setLoading(false)
    }
  }, [monthFrom, monthTo])

  useEffect(() => {
    void fetchIncome()
  }, [fetchIncome])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs text-zinc-500 mb-1">開始月</label>
          <input
            type="month"
            value={monthFrom.slice(0, 7)}
            onChange={(e) => setMonthFrom(`${e.target.value}-01`)}
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 mb-1">終了月</label>
          <input
            type="month"
            value={monthTo.slice(0, 7)}
            onChange={(e) => setMonthTo(`${e.target.value}-01`)}
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <Button size="sm" variant="outline" onClick={fetchIncome} disabled={loading} className="text-xs h-9">
          {loading ? '取得中…' : '更新'}
        </Button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {income && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'サブスク合計', value: jpyFmt(income.subscription_total) },
              { label: '成果報酬合計', value: jpyFmt(income.fee_total) },
              { label: '超過利益合計', value: jpyFmt(income.yield_excess_total) },
              { label: 'UATa 純収益', value: jpyFmt(income.uata_income_total), accent: true },
            ].map(({ label, value, accent }) => (
              <Card key={label} className="bg-zinc-900 border-zinc-800">
                <CardContent className="pt-4 pb-3 px-4">
                  <p className="text-xs text-zinc-500 mb-1">{label}</p>
                  <p className={`text-base font-semibold ${accent ? 'text-indigo-400' : 'text-zinc-100'}`}>{value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-400">収益内訳</CardTitle>
            </CardHeader>
            <CardContent>
              <IncomeChartRecharts data={chartData} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const MONTH_OPTIONS = buildMonthOptions()

type Tab = 'users' | 'income'

function AdminFeesContent() {
  const { token } = useAuth()
  const [tab, setTab] = useState<Tab>('users')
  const [month, setMonth] = useState(todayMonthStr())
  const [users, setUsers] = useState<AllUsersFeeItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showFinalize, setShowFinalize] = useState(false)

  const fetchUsers = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ month })
      const data = await apiFetch<AllUsersFeeItem[]>(`/api/v1/fees/all-users?${params.toString()}`)
      setUsers(data)
    } catch {
      setError('ユーザーデータの取得に失敗しました')
    } finally {
      setLoading(false)
    }
  }, [token, month])

  useEffect(() => {
    if (tab === 'users') void fetchUsers()
  }, [tab, fetchUsers])

  return (
    <div className="min-h-screen bg-zinc-950">
      <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-zinc-100">手数料管理</h1>
          <div className="flex gap-1">
            {(['users', 'income'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                  tab === t
                    ? 'bg-zinc-800 text-zinc-100'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {t === 'users' ? 'ユーザー別' : 'UATa 収益'}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="px-4 py-4 max-w-6xl mx-auto">
        {tab === 'users' && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <label className="text-xs text-zinc-500">対象月</label>
              <select
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {MONTH_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {loading && (
              <div className="space-y-2">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-10 bg-zinc-800 rounded" />
                ))}
              </div>
            )}

            {error && !loading && (
              <p className="text-sm text-red-400">{error}</p>
            )}

            {!loading && !error && (
              <Card className="bg-zinc-900 border-zinc-800">
                <CardContent className="pt-4">
                  <UsersTable items={users} onFinalize={() => setShowFinalize(true)} />
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {tab === 'income' && token && <IncomeSection token={token} />}
      </div>

      {showFinalize && token && (
        <FinalizeModal
          month={month}
          token={token}
          onClose={() => {
            setShowFinalize(false)
            void fetchUsers()
          }}
        />
      )}
    </div>
  )
}

export default function AdminFeesPage() {
  return (
    <AuthGuard adminOnly>
      <AdminFeesContent />
    </AuthGuard>
  )
}
