'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/admin/BorrowRatesPanel.tsx
//
// GHO / USDC 借入金利比較パネル。
// GET /api/aave/borrow-rates を 60 秒ごとにポーリングして表示する。
// recharts は SSR クラッシュ防止のため dynamic import で遅延ロード。

import dynamic from 'next/dynamic'
import { useEffect, useState, useCallback } from 'react'
import { useTranslations } from 'next-intl'

import { getBorrowRates, type BorrowRateComparison } from '@/lib/api/aave'

// Recharts コンポーネントを SSR 無効化で動的インポート
const BorrowRatesPanelRecharts = dynamic(
  () => import('./BorrowRatesPanelRecharts'),
  { ssr: false },
)

const POLL_INTERVAL_MS = 60_000 // 60 秒ごとに更新

export default function BorrowRatesPanel() {
  const t = useTranslations('BorrowRatesPanel')
  const [data, setData] = useState<BorrowRateComparison | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const result = await getBorrowRates()
      setData(result)
      setFetchError(false)
    } catch {
      setFetchError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchData])

  // APR を % 表示用の数値に変換（Decimal 文字列 → Number × 100）
  const toAprPct = (aprStr: string): number => {
    const n = Number(aprStr)
    return Number.isFinite(n) ? n * 100 : 0
  }

  const isGhoRecommended = data?.recommendation === 'GHO'
  const annualSavings = data ? Number(data.annual_savings_usd) : 0

  return (
    <div className="rounded-xl border border-zinc-700/40 bg-zinc-800/20 p-5">
      {/* ヘッダー */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-100">{t('title')}</h2>
          <p className="text-xs text-zinc-500 mt-0.5">{t('description')}</p>
        </div>
        {data && !fetchError && (
          <span
            className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
              isGhoRecommended
                ? 'border-green-500/30 bg-green-500/20 text-green-400'
                : 'border-blue-500/30 bg-blue-500/20 text-blue-400'
            }`}
          >
            {isGhoRecommended ? t('recommendGho') : t('recommendUsdc')}
          </span>
        )}
      </div>

      {/* エラー表示 */}
      {fetchError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400 mb-4">
          {t('fetchError')}
        </div>
      )}

      {/* API がエラーを返した場合（fail-open: error フィールドあり） */}
      {data?.error && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300 mb-4">
          {t('apiError', { message: data.error })}
        </div>
      )}

      {/* ローディング */}
      {loading && !data && (
        <div className="text-sm text-zinc-500 py-4 text-center">{t('loading')}</div>
      )}

      {/* 金利データ */}
      {data && !fetchError && (
        <>
          {/* 数値サマリー */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="rounded-lg border border-zinc-700/40 bg-zinc-800/40 px-3 py-2">
              <p className="text-xs text-zinc-500">{t('usdcApr')}</p>
              <p className="text-sm font-medium text-zinc-200 mt-1">
                {(toAprPct(data.usdc_apr)).toFixed(2)}%
              </p>
            </div>
            <div className="rounded-lg border border-zinc-700/40 bg-zinc-800/40 px-3 py-2">
              <p className="text-xs text-zinc-500">{t('ghoVariableApr')}</p>
              <p className="text-sm font-medium text-zinc-200 mt-1">
                {(toAprPct(data.gho_variable_apr)).toFixed(2)}%
              </p>
            </div>
            <div className="rounded-lg border border-zinc-700/40 bg-zinc-800/40 px-3 py-2">
              <p className="text-xs text-zinc-500">{t('ghoEffectiveApr')}</p>
              <p className="text-sm font-medium text-zinc-200 mt-1">
                {(toAprPct(data.gho_effective_apr)).toFixed(2)}%
              </p>
            </div>
          </div>

          {/* 年間節約額（GHO 推奨時のみ表示） */}
          {isGhoRecommended && Number.isFinite(annualSavings) && annualSavings > 0 && (
            <div className="rounded-lg border border-green-500/20 bg-green-500/10 px-4 py-2.5 mb-4">
              <p className="text-xs text-green-300">
                {t('annualSavings', { amount: annualSavings.toFixed(2) })}
              </p>
            </div>
          )}

          {/* グラフ */}
          <BorrowRatesPanelRecharts
            usdcAprPct={toAprPct(data.usdc_apr)}
            ghoVariableAprPct={toAprPct(data.gho_variable_apr)}
            ghoEffectiveAprPct={toAprPct(data.gho_effective_apr)}
            labels={{
              usdc: t('chartLabelUsdc'),
              ghoVariable: t('chartLabelGhoVariable'),
              ghoEffective: t('chartLabelGhoEffective'),
              yAxisLabel: t('chartYAxisLabel'),
            }}
          />
        </>
      )}
    </div>
  )
}
