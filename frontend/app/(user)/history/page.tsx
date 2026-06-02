// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState, useCallback, useEffect } from 'react'
import Link from 'next/link'
import {
  StatsCards,
  TransactionFilters,
  TransactionList,
} from './_components'
import type { Transaction, OperationType } from './_components'
import { apiFetch } from '@/lib/api/client'
import { Skeleton } from '@/components/ui/skeleton'
import AuthGuard from '@/components/AuthGuard'
import { getStoredToken } from '@/lib/auth'

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

interface TransactionAPIResponse {
  id: number
  user_id: number
  wallet_address: string | null
  operation: string // 'SUPPLY'|'WITHDRAW'|'BORROW'|'REPAY'
  asset: string
  amount: string // Decimal as string
  amount_usd: string // Decimal as string
  tx_hash: string | null
  chain: string
  status: string // 'pending'|'success'|'failed'
  gas_used: string | null
  gas_price_gwei: string | null
  is_dry_run: boolean
  created_at: string
}

interface TransactionListResponse {
  items: TransactionAPIResponse[]
  total: number
  limit: number
  offset: number
}

interface TransactionStatsResponse {
  total_count: number
  success_count: number
  total_amount_usd: string // Decimal as string
  total_gas_usd: string // Decimal as string
}

// ---------------------------------------------------------------------------
// Mapper
// ---------------------------------------------------------------------------

function mapToTransaction(item: TransactionAPIResponse): Transaction {
  return {
    id: String(item.id),
    type: item.operation as Transaction['type'],
    asset: item.asset,
    amount: parseFloat(item.amount),
    amountUSD: parseFloat(item.amount_usd),
    status: item.status as Transaction['status'],
    txHash: item.tx_hash ?? '',
    chain: item.chain as Transaction['chain'],
    timestamp: item.created_at,
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const LIMIT = 20
const CURRENT_YEAR = new Date().getFullYear()

async function downloadCryptactCsv(year: number | null): Promise<void> {
  const token = getStoredToken()
  const base = (process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? '').replace(/\/$/, '')
  const yearParam = year !== null ? `?year=${year}` : ''
  const url = `${base}/api/proposals/tax/cryptact-csv${yearParam}`
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`CSV取得失敗: ${res.status}`)
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = year ? `cryptact_aave_${year}.csv` : 'cryptact_aave.csv'
  a.click()
  URL.revokeObjectURL(href)
}

function HistoryPageContent() {
  const [activeType, setActiveType] = useState<OperationType>('ALL')
  const [csvYear, setCsvYear] = useState<number>(CURRENT_YEAR)
  const [csvDownloading, setCsvDownloading] = useState(false)
  const [csvError, setCsvError] = useState<string | null>(null)

  const handleCsvDownload = async () => {
    setCsvDownloading(true)
    setCsvError(null)
    try {
      await downloadCryptactCsv(csvYear)
    } catch {
      setCsvError('CSVのダウンロードに失敗しました')
    } finally {
      setCsvDownloading(false)
    }
  }
  // Initialize to 30-day range to match DateRangeFilter's default visual state
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | 'all'>(() => {
    const from = new Date()
    from.setDate(from.getDate() - 30)
    return { from, to: new Date() }
  })

  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [totalProfitUSD, setTotalProfitUSD] = useState(0)
  const [totalFeeUSD, setTotalFeeUSD] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)

  const fetchStats = useCallback(async () => {
    const stats = await apiFetch<TransactionStatsResponse>('/api/transactions/stats')
    setTotalCount(stats.total_count)
    setTotalProfitUSD(parseFloat(stats.total_amount_usd) * 0.042 * (30 / 365))
    setTotalFeeUSD(parseFloat(stats.total_gas_usd))
  }, [])

  const buildQuery = useCallback(
    (currentOffset: number) => {
      const params = new URLSearchParams()
      params.set('limit', String(LIMIT))
      params.set('offset', String(currentOffset))
      if (activeType !== 'ALL') params.set('operation', activeType)
      if (dateRange !== 'all') {
        params.set('date_from', dateRange.from.toISOString().split('T')[0])
        params.set('date_to', dateRange.to.toISOString().split('T')[0])
      }
      return params.toString()
    },
    [activeType, dateRange]
  )

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    setOffset(0)
    try {
      const [listRes] = await Promise.all([
        apiFetch<TransactionListResponse>(`/api/transactions?${buildQuery(0)}`),
        fetchStats(),
      ])
      setTransactions(listRes.items.map(mapToTransaction))
      setTotalCount(listRes.total)
    } catch {
      setError('データを取得できません')
    } finally {
      setLoading(false)
    }
  }, [buildQuery, fetchStats])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleLoadMore = async () => {
    setLoadingMore(true)
    try {
      const newOffset = offset + LIMIT
      const res = await apiFetch<TransactionListResponse>(
        `/api/transactions?${buildQuery(newOffset)}`
      )
      setTransactions((prev) => [...prev, ...res.items.map(mapToTransaction)])
      setOffset(newOffset)
    } catch {
      // silently ignore
    } finally {
      setLoadingMore(false)
    }
  }

  const hasMore = transactions.length < totalCount

  // -------------------------------------------------------------------------
  // Main render — filters are always mounted so their state is never reset
  // -------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Header */}
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-xl font-bold text-zinc-100">取引履歴</h1>
            <p className="text-sm text-zinc-400 mt-0.5">Aave操作の全履歴を確認できます</p>
          </div>
          <Link
            href="/fees"
            className="text-xs text-blue-400 hover:text-blue-300 underline underline-offset-2"
          >
            手数料明細を見る →
          </Link>
        </div>

        {/* 税務CSV (Cryptact) ダウンロード */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
          <div>
            <p className="text-sm font-medium text-zinc-200">税務CSV (Cryptact形式)</p>
            <p className="text-xs text-zinc-500 mt-0.5">
              実行済みAave操作をCryptact無料版フォーマットでエクスポートします
            </p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={csvYear}
              onChange={(e) => setCsvYear(Number(e.target.value))}
              className="text-sm bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - i).map((y) => (
                <option key={y} value={y}>{y}年</option>
              ))}
            </select>
            <button
              onClick={handleCsvDownload}
              disabled={csvDownloading}
              className="px-4 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white rounded-md transition-colors"
            >
              {csvDownloading ? 'ダウンロード中...' : 'CSVダウンロード'}
            </button>
          </div>
          {csvError && (
            <p className="text-xs text-red-400">{csvError}</p>
          )}
        </div>

        {/* Stats */}
        {loading ? (
          <div className="grid grid-cols-3 gap-4">
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-24 rounded-xl" />
          </div>
        ) : (
          <StatsCards
            totalCount={totalCount}
            totalProfitUSD={totalProfitUSD}
            totalFeeUSD={totalFeeUSD}
          />
        )}

        {/* Filters — always rendered so selected state persists across fetches */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <TransactionFilters
            activeType={activeType}
            onTypeChange={setActiveType}
            onDateRangeChange={setDateRange}
          />
        </div>

        {/* Transaction list or error */}
        {error ? (
          <div className="text-center space-y-3">
            <p className="text-sm text-red-400">{error}</p>
            <button onClick={fetchData} className="text-xs text-blue-400 underline">
              再試行
            </button>
          </div>
        ) : loading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-20 rounded-xl" />
            ))}
          </div>
        ) : (
          <TransactionList transactions={transactions} />
        )}

        {/* Load more */}
        {!loading && !error && hasMore && (
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="w-full py-3 text-sm text-zinc-400 hover:text-zinc-300 border border-zinc-800 rounded-xl"
          >
            {loadingMore ? '読み込み中...' : 'もっと見る'}
          </button>
        )}
      </div>
    </div>
  )
}


export default function HistoryPage() {
  return (
    <AuthGuard>
      <HistoryPageContent />
    </AuthGuard>
  )
}
