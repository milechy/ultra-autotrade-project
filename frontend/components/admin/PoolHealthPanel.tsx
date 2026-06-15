'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/admin/PoolHealthPanel.tsx
/**
 * Aave プール赤字監視パネル。
 * GET /api/aave/pool-health の結果を表示する。
 * ダミーデータ禁止 — データ未取得時は「データなし」表示。
 */

import { useEffect, useState, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { getPoolHealth, type PoolHealthResult } from '@/lib/api/aave'

export default function PoolHealthPanel() {
  const t = useTranslations('PoolHealthPanel')
  const [data, setData] = useState<PoolHealthResult | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const result = await getPoolHealth()
      setData(result)
      setLoadError(false)
    } catch {
      setData(null)
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60_000)
    return () => clearInterval(interval)
  }, [fetchData])

  const noData = t('noData')

  function formatDeficit(deficitUsd: string): string {
    const n = Number(deficitUsd)
    if (!Number.isFinite(n)) return noData
    if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`
    if (n >= 1_000) return `$${(n / 1_000).toFixed(2)}K`
    return `$${n.toFixed(2)}`
  }

  return (
    <div className="rounded-xl border border-zinc-700/40 bg-zinc-800/20 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-zinc-100">{t('title')}</h2>
        {data?.alert_triggered && (
          <span className="inline-flex items-center rounded-full border border-red-500/30 bg-red-500/20 px-2 py-0.5 text-xs font-semibold text-red-400">
            {t('alertActive')}
          </span>
        )}
      </div>

      {loading && (
        <p className="text-sm text-zinc-500">{t('loading')}</p>
      )}

      {!loading && loadError && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-400">
          {t('loadError')}
        </div>
      )}

      {!loading && data?.error && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 px-3 py-2 text-sm text-amber-300 mb-3">
          {data.error}
        </div>
      )}

      {!loading && !loadError && data && (
        <>
          <div className="flex items-center justify-between py-2 border-b border-zinc-800">
            <span className="text-sm text-zinc-500">{t('chain')}</span>
            <span className="text-sm font-medium text-zinc-200">{data.chain_name}</span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-zinc-800">
            <span className="text-sm text-zinc-500">{t('totalDeficit')}</span>
            <span className={`text-sm font-medium ${data.alert_triggered ? 'text-red-400' : 'text-zinc-200'}`}>
              {formatDeficit(data.total_deficit_usd)}
            </span>
          </div>

          {data.deficits.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-600">{t('noDeficits')}</p>
          ) : (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-medium text-zinc-500 mb-1">{t('assetBreakdown')}</p>
              {data.deficits.map((d) => (
                <div
                  key={d.asset_symbol}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg border ${
                    d.alert_triggered
                      ? 'border-red-500/30 bg-red-500/10'
                      : 'border-zinc-700/30 bg-zinc-800/30'
                  }`}
                >
                  <span className="text-sm font-medium text-zinc-300">{d.asset_symbol}</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm ${d.alert_triggered ? 'text-red-400' : 'text-zinc-300'}`}>
                      {formatDeficit(d.deficit_usd)}
                    </span>
                    {d.alert_triggered && (
                      <span className="text-xs text-red-400">{t('alert')}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-[11px] text-zinc-600">{t('autoRefresh')}</p>
        </>
      )}

      {!loading && !loadError && !data && (
        <p className="text-sm text-zinc-600">{noData}</p>
      )}
    </div>
  )
}
