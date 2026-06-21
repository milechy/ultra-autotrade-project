'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/dashboard/StressTestCard.tsx
//
// 清算リスク事前計算（LiquidationSentinel）のユーザー向け表示。
// GET /api/aave/stress-test の「価格 -10% / -20% 時の Health Factor」を表示する。
// 読み取り専用（情報提供のみ）。

import { useTranslations } from 'next-intl'
import { ShieldAlert, Loader2, RefreshCw } from 'lucide-react'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import type { StressTestResult } from '@/lib/api/aave'

/** HF 値に応じた文字色（≥1.6 安全 / ≥1.3 注意 / <1.3 危険 / null 不明）。 */
function hfColor(hf: number | null): string {
  if (hf === null) return 'text-zinc-500'
  if (hf >= 1.6) return 'text-emerald-400'
  if (hf >= 1.3) return 'text-amber-400'
  return 'text-red-400'
}

function fmtHf(value: string | null): { text: string; num: number | null } {
  if (value === null || value === '') return { text: '—', num: null }
  const n = Number(value)
  if (Number.isNaN(n)) return { text: '—', num: null }
  return { text: n.toFixed(2), num: n }
}

export function StressTestCard() {
  const t = useTranslations('StressTestCard')
  const { data, loading, error, refetch } = useAuthFetch<StressTestResult>(
    '/api/aave/stress-test',
    { refreshInterval: 300000 }, // 5分ごと
  )

  const current = fmtHf(data?.current_hf ?? null)
  // ポジション無し（担保なし）は current_hf が null。表示を「対象ポジションなし」にする。
  const hasPosition = !loading && !error && data != null && data.error == null && current.num != null

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-sky-400" />
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

      {!loading && !error && !hasPosition && (
        <p className="text-xs text-zinc-500 py-2">{t('noPosition')}</p>
      )}

      {hasPosition && data && (
        <>
          {/* 現在 HF */}
          <div className="space-y-1">
            <p className="text-xs text-zinc-500">{t('currentHf')}</p>
            <p className={`text-xl font-bold ${hfColor(current.num)}`}>{current.text}</p>
          </div>

          {/* 価格下落シナリオ */}
          <ul className="space-y-1.5" data-testid="stress-scenarios">
            {(data.scenarios ?? []).map((s, i) => {
              const sim = fmtHf(s.simulated_hf)
              const dropPct = Number(s.price_drop_pct)
              const dropLabel = Number.isNaN(dropPct) ? s.price_drop_pct : (dropPct * 100).toFixed(0)
              return (
                <li key={i} className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400">{t('scenario', { drop: dropLabel })}</span>
                  <span className={`font-semibold ${hfColor(sim.num)}`}>
                    HF {sim.text}
                  </span>
                </li>
              )
            })}
          </ul>

          <p className="text-[10px] text-zinc-600">{t('note')}</p>
        </>
      )}
    </div>
  )
}
