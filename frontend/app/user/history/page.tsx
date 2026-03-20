'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

export const dynamic = 'force-dynamic'

import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, ChevronLeft, ChevronRight, Filter } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { UserProviders } from '@/components/user/UserProviders'
import { getJson } from '@/lib/api/http'

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
          <h1 className="text-lg font-semibold">取引履歴</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowFilters(v => !v)}
              className="rounded-full p-1.5 text-muted-foreground hover:bg-muted"
              aria-label="フィルター"
            >
              <Filter className="h-4 w-4" />
            </button>
            <button
              onClick={fetchHistory}
              disabled={isLoading}
              className="rounded-full p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-50"
              aria-label="更新"
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
            className={`px-4 py-2 rounded-lg text-sm font-medium ${activeTab === 'aave' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'}`}
          >
            Aave操作履歴
          </button>
          <button
            onClick={() => setActiveTab('exchange')}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${activeTab === 'exchange' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'}`}
          >
            取引所履歴（Coming Soon）
          </button>
        </div>

        {activeTab === 'aave' && (
          <div className="space-y-3">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <p className="text-sm text-blue-600">Aave操作履歴はリバランス実行後に表示されます</p>
            </div>
          </div>
        )}

        {activeTab === 'exchange' && (
          <div className="relative">
            <div className="absolute inset-0 bg-white/80 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg">
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