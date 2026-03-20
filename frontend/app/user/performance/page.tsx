'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { convertUSDCtoJPY, formatJPY } from '@/lib/jpy-converter'
import { useAuth } from '@/lib/auth'
import type { PerformanceData, MonthlyPnl } from '@/components/transparency'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function MonthlyReportDownloadButton() {
  const { token } = useAuth()
  const [downloading, setDownloading] = useState(false)

  if (!token) return null

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const now = new Date()
      const year = now.getFullYear()
      const month = now.getMonth() + 1
      const res = await fetch(
        `${API_URL}/api/reports/monthly?year=${year}&month=${month}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const contentDisposition = res.headers.get('Content-Disposition') ?? ''
      const filenameMatch = contentDisposition.match(/filename="([^"]+)"/)
      const filename = filenameMatch ? filenameMatch[1] : `monthly_report_${year}_${String(month).padStart(2, '0')}.csv`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // ダウンロード失敗時はコンソールのみ（UIは状態をリセット）
    } finally {
      setDownloading(false)
    }
  }

  return (
    <button
      onClick={handleDownload}
      disabled={downloading}
      className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {downloading ? '取得中…' : '月次レポートDL'}
    </button>
  )
}

function WinRateBar({ rate }: { rate: number }) {
  const color = rate >= 70 ? 'bg-green-500' : rate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor =
    rate >= 70
      ? 'text-green-600 dark:text-green-400'
      : rate >= 50
      ? 'text-yellow-600 dark:text-yellow-400'
      : 'text-red-600 dark:text-red-400'
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">勝率</span>
        <span className={`text-lg font-bold ${textColor}`}>{rate.toFixed(1)}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${rate}%` }} />
      </div>
    </div>
  )
}

function PerformanceContent() {
  const [perf, setPerf] = useState<PerformanceData | null>(null)
  const [monthly, setMonthly] = useState<MonthlyPnl[]>([])
  const [totalPnlJpy, setTotalPnlJpy] = useState<number | null>(null)
  const [totalPnlUsdc] = useState<number>(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/api/transparency/performance?period_days=90`)
        .then(r => r.json())
        .catch(() => null),
      fetch(`${API_URL}/api/transparency/performance/monthly`)
        .then(r => r.json())
        .catch(() => []),
    ]).then(async ([perfData, monthlyData]) => {
      if (perfData) {
        setPerf(perfData as PerformanceData)
        const jpy = await convertUSDCtoJPY(perfData.total_pnl_usdc ?? 0).catch(() => 0)
        setTotalPnlJpy(jpy)
      }
      if (Array.isArray(monthlyData)) {
        setMonthly(monthlyData as MonthlyPnl[])
      }
    }).finally(() => setLoading(false))
  }, [totalPnlUsdc])

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    )
  }

  if (!perf) {
    return (
      <p className="text-center text-muted-foreground py-12">データを取得できませんでした</p>
    )
  }

  const gainJpy = perf.total_gain_jpy ?? 0
  const gainPositive = gainJpy >= 0

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-3">
        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-xs text-muted-foreground">勝率（{perf.period_days}日）</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            <p className="text-2xl font-bold">{Number(perf.win_rate ?? 0).toFixed(1)}%</p>
            <p className="text-xs text-muted-foreground">
              {perf.total_proposals}回提案 / {perf.positive_results}回プラス
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1 pt-3 px-3">
            <CardTitle className="text-xs text-muted-foreground">累計損益</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            <p className={`text-2xl font-bold ${gainPositive ? 'text-green-600' : 'text-red-600'}`}>
              {gainPositive ? '+' : ''}¥{Number(gainJpy).toLocaleString('ja-JP')}
            </p>
            {totalPnlJpy !== null && (
              <p className="text-xs text-muted-foreground">
                ≈ {formatJPY(totalPnlJpy)} (USDC換算)
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Win rate bar */}
      <Card>
        <CardContent className="pt-4">
          <WinRateBar rate={Number(perf.win_rate ?? 0)} />
          <p className="text-xs text-muted-foreground mt-3">
            平均損益: {gainPositive ? '+' : ''}¥{Number(perf.avg_gain_per_trade_jpy ?? 0).toLocaleString('ja-JP')} / 回
          </p>
        </CardContent>
      </Card>

      {/* Monthly chart */}
      {monthly.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">月次損益</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={monthly} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: string) => v.slice(5)}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: number) => `¥${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(v: number) => [formatJPY(v), '損益']}
                  labelFormatter={(l: string) => `${l}月`}
                />
                <Bar dataKey="gain_jpy" radius={[4, 4, 0, 0]}>
                  {monthly.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.gain_jpy >= 0 ? '#16a34a' : '#dc2626'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-muted-foreground text-center">
        ※ 実績は将来の結果を保証しません
      </p>
    </div>
  )
}

export default function PerformancePage() {
  return (
    <main className="px-4 py-6 max-w-md mx-auto">
      <div className="mb-4 flex items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">パフォーマンス</h1>
          <p className="text-xs text-muted-foreground mt-1">AI提案の実績サマリー</p>
        </div>
        <MonthlyReportDownloadButton />
      </div>
      <ErrorBoundary>
        <PerformanceContent />
      </ErrorBoundary>
    </main>
  )
}