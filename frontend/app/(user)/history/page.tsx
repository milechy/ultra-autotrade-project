// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState, useCallback, useEffect } from 'react'
import {
  StatsCards,
  TransactionFilters,
  TransactionList,
} from './_components'
import type { Transaction, OperationType } from './_components'
import { apiFetch } from '@/lib/api/client'
import { Skeleton } from '@/components/ui/skeleton'

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

export default function HistoryPage() {
  const [activeType, setActiveType] = useState<OperationType>('ALL')
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
        <div>
          <h1 className="text-xl font-bold text-zinc-100">取引履歴</h1>
          <p className="text-sm text-zinc-400 mt-0.5">Aave操作の全履歴を確認できます</p>
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
