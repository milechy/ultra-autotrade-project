'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

export const dynamic = 'force-dynamic'

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { RefreshCw, ChevronLeft, ChevronRight, Filter, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { UserProviders } from '@/components/user/UserProviders'
import { getJson } from '@/lib/api/http'
import { apiFetch } from '@/lib/api/client'

type TradeStatus = 'SUCCESS' | 'FAILED' | 'SKIPPED'
type TradeAction = 'BUY' | 'SELL'

type TradeRecord = {
  id: string
  created_at: string
  symbol: string
  action: TradeAction
  quantity: string
  filled_price: string | null
  fee: string | null
  status: TradeStatus
  pnl: string | null
}

type HistoryResponse = {
  items: TradeRecord[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 20

// ---- Aave transaction types ----

type AaveTransactionStatus = 'pending' | 'success' | 'failed'
type AaveOperation = 'SUPPLY' | 'WITHDRAW' | 'BORROW' | 'REPAY'

type AaveTransaction = {
  id: number
  operation: AaveOperation
  asset: string
  amount: string
  amount_usd: string
  tx_hash: string | null
  chain: string
  status: AaveTransactionStatus
  is_dry_run: boolean
  created_at: string
}

type AaveTransactionListResponse = {
  items: AaveTransaction[]
  total: number
  limit: number
  offset: number
}

const AAVE_PAGE_SIZE = 20

const aaveOperationConfig: Record<AaveOperation, { label: string; className: string }> = {
  SUPPLY: { label: 'SUPPLY', className: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' },
  WITHDRAW: { label: 'WITHDRAW', className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' },
  BORROW: { label: 'BORROW', className: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400' },
  REPAY: { label: 'REPAY', className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400' },
}

function getExplorerUrl(txHash: string, chain: string): string {
  if (chain === 'arbitrum') return `https://arbiscan.io/tx/${txHash}`
  if (chain === 'arbitrum-sepolia') return `https://sepolia.arbiscan.io/tx/${txHash}`
  if (chain === 'base-sepolia') return `https://sepolia.basescan.org/tx/${txHash}`
  if (chain === 'base') return `https://basescan.org/tx/${txHash}`
  return `https://arbiscan.io/tx/${txHash}`
}

function AaveHistoryTab() {
  const [transactions, setTransactions] = useState<AaveTransaction[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [operationFilter, setOperationFilter] = useState<AaveOperation | ''>('')
  const t = useTranslations('History')
  const tCommon = useTranslations('Common')

  const fetchAave = useCallback(async (newOffset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(AAVE_PAGE_SIZE))
      params.set('offset', String(newOffset))
      if (operationFilter) params.set('operation', operationFilter)
      const res = await apiFetch<AaveTransactionListResponse>(`/api/transactions?${params.toString()}`)
      if (newOffset === 0) {
        setTransactions(res.items)
      } else {
        setTransactions(prev => [...prev, ...res.items])
      }
      setTotal(res.total)
      setOffset(newOffset)
    } catch {
      setError(t('fetchError'))
    } finally {
      setLoading(false)
    }
  }, [operationFilter])

  useEffect(() => {
    fetchAave(0)
  }, [fetchAave])

  const hasMore = transactions.length < total

  if (loading && transactions.length === 0) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-16 rounded-lg" />)}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-950 dark:border-red-800 p-4 text-center space-y-2">
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        <button onClick={() => fetchAave(0)} className="text-xs text-blue-500 underline">{tCommon('retry')}</button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Filter */}
      <div className="flex gap-2 flex-wrap">
        {(['', 'SUPPLY', 'WITHDRAW', 'BORROW', 'REPAY'] as const).map(op => (
          <button
            key={op}
            onClick={() => setOperationFilter(op as AaveOperation | '')}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              operationFilter === op
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            {op === '' ? tCommon('all') : op}
          </button>
        ))}
      </div>

      {transactions.length === 0 ? (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          {t('noAaveHistory')}
        </div>
      ) : (
        <>
          <div className="text-xs text-muted-foreground">{t('totalCount', { total })}</div>
          <div className="space-y-2">
            {transactions.map(tx => {
              const opCfg = aaveOperationConfig[tx.operation as AaveOperation] ?? aaveOperationConfig.SUPPLY
              const stVariant = tx.status === 'success' ? 'default' : tx.status === 'failed' ? 'destructive' : 'secondary'
              const stLabel = tx.status === 'success' ? t('success') : tx.status === 'failed' ? t('failed') : t('pending')
              return (
                <div key={tx.id} className="rounded-lg border bg-card p-3 space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${opCfg.className}`}>
                        {opCfg.label}
                      </span>
                      <span className="font-semibold text-sm">{tx.asset}</span>
                      {tx.is_dry_run && (
                        <span className="rounded-full bg-zinc-200 dark:bg-zinc-700 px-2 py-0.5 text-xs text-zinc-500">
                          DRY RUN
                        </span>
                      )}
                    </div>
                    <Badge variant={stVariant} className="text-xs shrink-0">{stLabel}</Badge>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{parseFloat(tx.amount).toLocaleString()} {tx.asset}</span>
                    <span className="text-muted-foreground text-xs">${parseFloat(tx.amount_usd).toLocaleString()}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {new Date(tx.created_at).toLocaleString('ja-JP', {
                        timeZone: 'Asia/Tokyo',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                    {tx.tx_hash && (
                      <a
                        href={getExplorerUrl(tx.tx_hash, tx.chain)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-blue-500 hover:text-blue-400 font-mono"
                      >
                        {tx.tx_hash.slice(0, 6)}...{tx.tx_hash.slice(-4)}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          {hasMore && (
            <button
              onClick={() => fetchAave(offset + AAVE_PAGE_SIZE)}
              disabled={loading}
              className="w-full py-2 text-sm text-muted-foreground hover:text-foreground border border-muted rounded-lg"
            >
              {loading ? tCommon('loading') : t('loadMore')}
            </button>
          )}
        </>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: TradeStatus }) {
  const map: Record<TradeStatus, { label: string; variant: 'default' | 'destructive' | 'secondary' | 'outline' }> = {
    SUCCESS: { label: '成功', variant: 'default' },
    FAILED: { label: '失敗', variant: 'destructive' },
    SKIPPED: { label: 'スキップ', variant: 'secondary' },
  }
  const { label, variant } = map[status]
  return <Badge variant={variant}>{label}</Badge>
}

function ActionBadge({ action }: { action: TradeAction }) {
  return (
    <Badge variant={action === 'BUY' ? 'default' : 'destructive'} className="text-xs">
      {action}
    </Badge>
  )
}

function PnlCell({ pnl }: { pnl: string | null }) {
  if (pnl == null) return <span className="text-muted-foreground">—</span>
  const val = parseFloat(pnl)
  const colored = val >= 0 ? 'text-green-600' : 'text-red-600'
  const prefix = val >= 0 ? '+' : ''
  return <span className={`font-medium ${colored}`}>{prefix}{(isNaN(val) ? 0 : val).toFixed(2)}</span>
}

function HistoryTable({ records }: { records: TradeRecord[] }) {
  if (records.length === 0) {
    return (
      <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
        該当する取引履歴がありません
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="min-w-full text-sm">
        <thead className="border-b bg-muted/50">
          <tr>
            <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">日時</th>
            <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">ペア</th>
            <th className="px-3 py-2.5 text-left font-medium text-muted-foreground">種別</th>
            <th className="px-3 py-2.5 text-right font-medium text-muted-foreground">数量</th>
            <th className="px-3 py-2.5 text-right font-medium text-muted-foreground">約定価格</th>
            <th className="px-3 py-2.5 text-right font-medium text-muted-foreground">損益</th>
            <th className="px-3 py-2.5 text-center font-medium text-muted-foreground">状態</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {records.map(r => (
            <tr key={r.id} className="hover:bg-muted/30 transition-colors">
              <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                {r.created_at
                  ? new Date(r.created_at).toLocaleString('ja-JP', {
                      timeZone: 'Asia/Tokyo',
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : '—'}
              </td>
              <td className="px-3 py-2.5 font-medium whitespace-nowrap">{r.symbol}</td>
              <td className="px-3 py-2.5">
                <ActionBadge action={r.action} />
              </td>
              <td className="px-3 py-2.5 text-right">{r.quantity}</td>
              <td className="px-3 py-2.5 text-right">
                {r.filled_price ? `$${parseFloat(r.filled_price).toFixed(2)}` : '—'}
              </td>
              <td className="px-3 py-2.5 text-right">
                <PnlCell pnl={r.pnl} />
              </td>
              <td className="px-3 py-2.5 text-center">
                <StatusBadge status={r.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function HistoryPage() {
  const { token } = useAuth()
  const t = useTranslations('History')
  const tCommon = useTranslations('Common')
  const [activeTab, setActiveTab] = useState<'exchange' | 'aave'>('aave')
  const [records, setRecords] = useState<TradeRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [actionFilter, setActionFilter] = useState<TradeAction | ''>('')
  const [showFilters, setShowFilters] = useState(false)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const fetchHistory = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
      })
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo) params.set('date_to', dateTo)
      if (actionFilter) params.set('action', actionFilter)

      const data = await getJson<HistoryResponse>(
        `/exchange/history?${params.toString()}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setRecords(data.items)
      setTotal(data.total)
    } catch {
      // endpoint may not exist yet — show empty state
      setRecords([])
      setTotal(0)
    } finally {
      setIsLoading(false)
    }
  }, [token, page, dateFrom, dateTo, actionFilter])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  const handleFilterApply = () => {
    setPage(1)
    setShowFilters(false)
    fetchHistory()
  }

  const handleFilterReset = () => {
    setDateFrom('')
    setDateTo('')
    setActionFilter('')
    setPage(1)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="flex items-center justify-between px-4 py-3">
          <h1 className="text-lg font-semibold">{t('title')}</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowFilters(v => !v)}
              className="rounded-full p-1.5 text-muted-foreground hover:bg-muted"
              aria-label={tCommon('filter')}
            >
              <Filter className="h-4 w-4" />
            </button>
            <button
              onClick={fetchHistory}
              disabled={isLoading}
              className="rounded-full p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-50"
              aria-label={t('refresh')}
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      <div className="px-4 py-4 space-y-4">
        {/* Tab switcher */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setActiveTab('aave')}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${activeTab === 'aave' ? 'bg-blue-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-600'}`}
          >
            {t('aaveTab')}
          </button>
          <button
            onClick={() => setActiveTab('exchange')}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${activeTab === 'exchange' ? 'bg-blue-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-600'}`}
          >
            {t('exchangeTab')}
          </button>
        </div>

        {activeTab === 'aave' && <AaveHistoryTab />}

        {activeTab === 'exchange' && (
          <div className="relative">
            <div className="absolute inset-0 bg-white dark:bg-gray-900/80 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg">
              <p className="text-gray-500 font-medium">Coming Soon — Phase 2で対応予定</p>
            </div>
            <div className="pointer-events-none select-none opacity-50">
              {showFilters && (
                <div className="rounded-lg border p-4 space-y-3">
                  <h2 className="text-sm font-medium">フィルター</h2>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs text-muted-foreground">開始日</label>
                      <Input
                        type="date"
                        value={dateFrom}
                        onChange={e => setDateFrom(e.target.value)}
                        className="text-sm"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-muted-foreground">終了日</label>
                      <Input
                        type="date"
                        value={dateTo}
                        onChange={e => setDateTo(e.target.value)}
                        className="text-sm"
                      />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">アクション</label>
                    <div className="flex gap-2">
                      {(['', 'BUY', 'SELL'] as const).map(v => (
                        <button
                          key={v}
                          onClick={() => setActionFilter(v as TradeAction | '')}
                          className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                            actionFilter === v
                              ? 'bg-primary text-primary-foreground'
                              : 'bg-muted text-muted-foreground hover:bg-muted/80'
                          }`}
                        >
                          {v === '' ? '全て' : v}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" className="flex-1" onClick={handleFilterApply}>
                      適用
                    </Button>
                    <Button size="sm" variant="outline" className="flex-1" onClick={handleFilterReset}>
                      リセット
                    </Button>
                  </div>
                </div>
              )}

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {isLoading ? (
                <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                  <RefreshCw className="mb-3 h-8 w-8 animate-spin" />
                  <p className="text-sm">読み込み中...</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>全 {total} 件</span>
                    <span>ページ {page} / {totalPages}</span>
                  </div>

                  <HistoryTable records={records} />

                  {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2">
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => setPage(p => Math.max(1, p - 1))}
                        disabled={page <= 1}
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="text-sm">
                        {page} / {totalPages}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                        disabled={page >= totalPages}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function TradeHistoryPage() {
  return (
    <UserProviders>
      <AuthGuard>
        <HistoryPage />
      </AuthGuard>
    </UserProviders>
  )
}