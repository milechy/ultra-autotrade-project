'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/dashboard/UnifiedPortfolioCard.tsx
//
// 統合ポートフォリオ（消費者個人）表示カード。GET /api/portfolio/unified の grand_total +
// ソース別配分（Aave 純資産 / Privy Wallet）を表示。fail-open（degraded 警告）対応。

import { useTranslations } from 'next-intl'
import { Layers, Loader2, RefreshCw, AlertTriangle } from 'lucide-react'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import type { UnifiedPortfolioView } from '@/lib/api/portfolio'

const SOURCE_LABEL_KEY: Record<string, string> = {
  aave: 'sourceAave',
  wallet: 'sourceWallet',
  cex: 'sourceCex',
}

function fmtUsd(value: string | null | undefined): string {
  if (value == null) return '—'
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function UnifiedPortfolioCard() {
  const t = useTranslations('UnifiedPortfolioCard')
  const { data, loading, error, refetch } = useAuthFetch<UnifiedPortfolioView>(
    '/api/portfolio/unified',
    { refreshInterval: 300000 }, // 5分ごと
  )

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-zinc-400">{t('title')}</h2>
        </div>
        <button
          onClick={() => void refetch()}
          aria-label={t('refresh')}
          className="p-1 rounded hover:bg-zinc-800 transition-colors"
        >
          <RefreshCw className="h-3 w-3 text-zinc-500" />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-2">
          <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />
          <span className="text-xs text-zinc-500">{t('loading')}</span>
        </div>
      )}

      {!loading && error && <p className="text-xs text-red-400 py-2">{t('fetchError')}</p>}

      {!loading && !error && data && (
        <>
          {/* 合計 */}
          <div className="space-y-1">
            <p className="text-xs text-zinc-500">{t('grandTotal')}</p>
            <p className="text-xl font-bold text-zinc-100">${fmtUsd(data.grand_total_usd)}</p>
          </div>

          {/* ソース別配分（available のみ） */}
          <ul className="space-y-1.5" data-testid="unified-allocations">
            {data.allocations
              .filter((a) => a.available && a.source !== 'cex')
              .map((a) => (
                <li key={a.source} className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400">{t(SOURCE_LABEL_KEY[a.source] ?? 'sourceWallet')}</span>
                  <span className="text-zinc-300">
                    ${fmtUsd(a.total_usd)}{' '}
                    <span className="text-zinc-500">({Number(a.allocation_pct).toFixed(1)}%)</span>
                  </span>
                </li>
              ))}
          </ul>

          {/* Health Factor（Aave available 時のみ） */}
          {data.health_factor != null && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-400">{t('healthFactor')}</span>
              <span className="text-zinc-300">{Number(data.health_factor).toFixed(2)}</span>
            </div>
          )}

          {/* fail-open: 一部ソース取得失敗時の警告 */}
          {data.degraded && (
            <div className="flex items-center gap-1.5 text-[10px] text-amber-500">
              <AlertTriangle className="h-3 w-3" />
              <span>{t('degraded', { available: data.sources_available, total: data.sources_total })}</span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
