'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { AssetIcon } from '@/components/shared'
import { useWallet } from '@/hooks/useWallet'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/api/client'

interface Position {
  symbol: string
  supplied: number
  borrowed: number
  supplyApr: number
  usdValue: number
}

interface PortfolioCurrentResponse {
  total_value_usd: string
  total_supply_usd: string
  total_borrow_usd: string
  health_factor: string | null
  positions_json: Array<{
    symbol: string
    supplied: number
    borrowed: number
    supplyApr: number
    usdValue: number
  }> | null
  has_data: boolean
}

function PositionCard({ pos, t }: { pos: Position; t: ReturnType<typeof useTranslations> }) {
  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AssetIcon symbol={pos.symbol} size="md" />
            <div>
              <p className="text-sm font-semibold text-white">{pos.symbol}</p>
              <p className="text-xs text-zinc-500">Supply APR {Number(pos.supplyApr).toFixed(2)}%</p>
            </div>
          </div>
          <div className="text-right flex-1 px-3">
            <p className="text-xs text-zinc-500">{t('supplyBorrow')}</p>
            <p className="text-sm font-medium text-white">
              {pos.supplied.toLocaleString()} / {pos.borrowed.toLocaleString()}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-zinc-500">{t('usdValue')}</p>
            <p className="text-sm font-semibold text-white">${pos.usdValue.toLocaleString()}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function PositionList() {
  const { isConnected } = useWallet()
  const { token, isLoading: authLoading } = useAuth()
  const t = useTranslations('Dashboard')
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const fetchPositions = useCallback(async () => {
    if (!token) return
    setError(false)
    setLoading(true)
    try {
      const res = await apiFetch<PortfolioCurrentResponse>('/api/portfolio/current')
      setPositions(res?.positions_json ?? [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    if (authLoading) return
    fetchPositions()
  }, [fetchPositions, isConnected, authLoading])

  // 30-second auto-refresh — only when authenticated
  useEffect(() => {
    if (!isConnected || !token) return
    const id = setInterval(() => fetchPositions(), 30_000)
    return () => clearInterval(id)
  }, [isConnected, fetchPositions, token])

  if (authLoading || loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-20 rounded-xl" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-2 py-6">
        <p className="text-sm text-zinc-400 text-center">{t('fetchError')}</p>
        <button
          onClick={() => { setLoading(true); fetchPositions() }}
          className="text-xs text-blue-400 hover:text-blue-300 underline"
        >
          {t('retry')}
        </button>
      </div>
    )
  }

  if (positions.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center space-y-3">
        <p className="text-sm text-zinc-400">{t('noPositions2')}</p>
        <p className="text-sm text-zinc-500">{t('approvePrompt')}</p>
        <Link href="/user/approve" className="text-xs text-blue-400 hover:text-blue-300 underline">
          {t('goToApprove')}
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {positions.map((pos) => (
        <PositionCard key={pos.symbol} pos={pos} t={t} />
      ))}
    </div>
  )
}
