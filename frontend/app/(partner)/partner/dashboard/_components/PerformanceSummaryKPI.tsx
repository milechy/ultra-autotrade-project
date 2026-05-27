'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { DollarSign, TrendingUp, Users, Shield, Wallet, AlertTriangle } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { fetchPerformance, type PerformanceResponse } from '@/lib/api/allocations'
import { getStoredToken } from '@/lib/auth'
import { useWalletBalance } from '@/hooks/useWalletBalance'

function fmtUsd(v: number | undefined | null): string {
  const n = Number(v ?? 0)
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(n)
}

function fmtPct(v: number | undefined | null): string {
  const n = Number(v ?? 0)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function pnlColor(v: number): string {
  if (v > 0) return 'text-green-600 dark:text-green-400'
  if (v < 0) return 'text-red-600 dark:text-red-400'
  return 'text-muted-foreground'
}

function hfColor(hf: number | null): string {
  if (hf === null) return 'text-muted-foreground'
  if (hf > 1.8) return 'text-green-600 dark:text-green-400'
  if (hf >= 1.6) return 'text-yellow-500 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}

function fmtTokenAmount(v: string | number | undefined | null, maxFractionDigits = 4): string {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '0'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: maxFractionDigits,
  }).format(n)
}

export default function PerformanceSummaryKPI() {
  const [data, setData] = useState<PerformanceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const { data: walletBalance, loading: walletLoading } = useWalletBalance()

  useEffect(() => {
    const load = () => {
      const token = getStoredToken()
      if (!token) return
      fetchPerformance(token)
        .then(setData)
        .catch(() => setData(null))
        .finally(() => setLoading(false))
    }

    setLoading(true)
    load()
    const id = setInterval(load, 300000)
    return () => clearInterval(id)
  }, [])

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    )
  }

  // backend returns flat PerformanceSummary directly (no .summary wrapper)
  // Number() coercion handles Decimal strings from the API (e.g. "1000.000000")
  const supplyUsd = Number(data?.total_supply_usd ?? 0)
  const allocatedUsd = Number(data?.total_allocated_usd ?? 0)
  const totalPnlUsd = data != null ? supplyUsd - allocatedUsd : 0
  const totalPnlPct =
    data != null && allocatedUsd > 0
      ? (totalPnlUsd / allocatedUsd) * 100
      : 0
  const testerCount = data?.testers.length ?? 0
  const hf = data?.health_factor != null ? Number(data.health_factor) : null

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      {/* 運用総額 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">運用総額</CardTitle>
          <DollarSign className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {data != null ? `$${fmtUsd(supplyUsd)}` : '—'}
          </div>
        </CardContent>
      </Card>

      {/* 全体損益 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">全体損益</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {data != null ? (
            <>
              <div className={`text-2xl font-bold ${pnlColor(totalPnlUsd)}`}>
                {totalPnlUsd >= 0 ? '+' : ''}${fmtUsd(Math.abs(totalPnlUsd))}
              </div>
              <div className={`text-xs mt-1 ${pnlColor(totalPnlPct)}`}>
                {fmtPct(totalPnlPct)}
              </div>
            </>
          ) : (
            <div className="text-2xl font-bold">—</div>
          )}
        </CardContent>
      </Card>

      {/* テスター数 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">テスター数</CardTitle>
          <Users className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {data != null ? testerCount : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">人</div>
        </CardContent>
      </Card>

      {/* Health Factor */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Health Factor</CardTitle>
          <Shield className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${hfColor(hf)}`}>
            {hf != null ? hf.toFixed(2) : '—'}
          </div>
          {hf != null && (
            <div className={`text-xs mt-1 ${hfColor(hf)}`}>
              {hf > 1.8 ? '安全' : hf >= 1.6 ? '注意' : '危険'}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ウォレット残高 (Base) — USDC + ETH on Base mainnet。Aave supply 分は含まない */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            ウォレット残高 (Base)
          </CardTitle>
          <div className="flex items-center gap-1">
            {walletBalance?.fallback_used && (
              <AlertTriangle
                className="h-4 w-4 text-yellow-500"
                aria-label="価格またはRPC取得失敗 (フォールバック使用中)"
              />
            )}
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </div>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {walletLoading
              ? '—'
              : walletBalance != null
                ? `$${fmtUsd(Number(walletBalance.total_usd))}`
                : '—'}
          </div>
          {walletBalance != null && (
            <div className="text-xs text-muted-foreground mt-1">
              ETH {fmtTokenAmount(walletBalance.eth_balance)} / USDC{' '}
              {fmtTokenAmount(walletBalance.usdc_balance, 2)}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
