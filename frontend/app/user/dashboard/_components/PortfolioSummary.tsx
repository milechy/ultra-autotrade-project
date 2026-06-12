'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useCallback } from 'react'
import { Wallet, RefreshCw } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { KPICard, HealthFactorGauge, StatusBadge } from '@/components/shared'
import { useWallet } from '@/hooks/useWallet'
import { useAaveV3 } from '@/hooks/useAaveV3'
import { useAutomationStatus } from '@/components/user/UserProviders'
import type { AaveUserAccountData } from '@/types/web3'

function formatUSD(raw: bigint): string {
  const usd = Number(raw) / 1e8
  return usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function parseHealthFactor(raw: bigint): number | null {
  // MaxUint256 means no borrow (infinite HF) → display as null
  if (raw >= BigInt('0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF')) {
    return null
  }
  return Number(raw) / 1e18
}

export function PortfolioSummary() {
  const { address, isConnected } = useWallet()
  const { getUserAccountData } = useAaveV3()
  const { systemStatus, isStopped } = useAutomationStatus()
  const t = useTranslations('Dashboard')
  const [data, setData] = useState<AaveUserAccountData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = useCallback(async (silent = false) => {
    if (!isConnected || !address) return
    if (!silent) setLoading(true)
    else setRefreshing(true)
    setError(null)
    try {
      const result = await getUserAccountData(address)
      setData(result)
    } catch (e) {
      if (!silent) setError(e instanceof Error ? e.message : t('fetchDataFailed'))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [isConnected, address, getUserAccountData])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // 30-second auto-refresh (stale-while-revalidate)
  useEffect(() => {
    if (!isConnected) return
    const id = setInterval(() => {
      fetchData(true)
    }, 30_000)
    return () => clearInterval(id)
  }, [isConnected, fetchData])

  if (!isConnected) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center">
        <p className="text-sm text-zinc-400">{t('connectWallet')}</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center space-y-3">
        <p className="text-sm text-red-400">{error}</p>
        <button
          onClick={() => fetchData()}
          className="text-xs text-blue-400 hover:text-blue-300 underline"
        >
          {t('retry')}
        </button>
      </div>
    )
  }

  const collateralUSD = data ? formatUSD(data.totalCollateralBase) : '—'
  const healthFactor = data ? parseHealthFactor(data.healthFactor) : null

  return (
    <div className="space-y-4">
      {isStopped && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 flex items-start gap-2">
          <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-red-400" />
          <p className="text-sm text-red-400 font-medium">
            {t('emergencyStop')}
          </p>
        </div>
      )}
      {refreshing && (
        <div className="flex items-center gap-1.5 text-xs text-zinc-500">
          <RefreshCw className="h-3 w-3 animate-spin" />
          <span>{t('refreshing')}</span>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <KPICard
          label={t('totalAssetLabel')}
          value={collateralUSD}
          prefix="$"
          icon={Wallet}
        />
        <Card className="border-zinc-800 bg-zinc-900">
          <CardHeader className="pb-2 pt-4 px-4">

          </CardHeader>
          <CardContent className="px-4 pb-4">
            <HealthFactorGauge value={healthFactor} size="lg" />
          </CardContent>
        </Card>
        <Card className="border-zinc-800 bg-zinc-900">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium text-zinc-400">{t('operationStatus')}</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <StatusBadge status={systemStatus} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
