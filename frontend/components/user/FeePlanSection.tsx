// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

// B-1: 料金プラン / Tier別月額 の事前提示 UX。
// 料率は GET /api/v1/fees/config から取得（ハードコード禁止）。
// 文言はすべて i18n (FeePricing namespace) 経由で、月利/月額表記は B-5 法務の
// 結論を後から差し替え可能な構造にしている。
// 徴収は現在停止中 (ENABLE_MONTHLY_FEE_BATCH=0 / FEE_TRANSFER_ENABLED=false) のため、
// 「現在は無料」である旨を notActiveNote で明示する（規約第7条と整合）。

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { apiFetch } from '@/lib/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface FeeConfig {
  tier_thresholds_jpy: number[]
  tier_fee_rates: number[]
  subscription_rates: Record<string, number>
}

// tier_fee_rates / tier_thresholds_jpy のインデックス順（LOWER / MIDDLE / UPPER）。
const TIER_KEYS = ['lower', 'middle', 'upper'] as const
// subscription_rates のキー（RiskMode 内部値）。
const RISK_KEYS = ['conservative', 'balanced', 'aggressive'] as const

function pct(rate: number): string {
  // 0.003 → "0.3", 0.3 → "30"。金額計算ではなく表示用なので通常の丸めで良い。
  return String(Number((rate * 100).toFixed(2)))
}

function jpy(v: number): string {
  // ロケール非依存の表示（¥1,000,000）。i18n テンプレは前後の語だけを担う。
  return `¥${Math.round(v).toLocaleString()}`
}

export default function FeePlanSection() {
  const t = useTranslations('FeePricing')
  const [config, setConfig] = useState<FeeConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    apiFetch<FeeConfig>('/api/v1/fees/config')
      .then((c) => {
        if (alive) setConfig(c)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  if (loading) {
    return <Skeleton className="h-56 rounded-xl bg-zinc-800" />
  }

  // fail-open: 料率が取れない場合はハードコードで代替せず、セクションごと非表示にする。
  if (failed || !config) {
    return null
  }

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-zinc-100">{t('title')}</CardTitle>
        <p className="text-xs text-zinc-500 mt-1">{t('subtitle')}</p>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* 月額利用料（サブスク）: risk mode 別 */}
        <section>
          <h3 className="text-sm font-semibold text-zinc-200 mb-2">{t('subscriptionTitle')}</h3>
          <div className="grid grid-cols-3 gap-2">
            {RISK_KEYS.map((rk) => {
              const rate = config.subscription_rates?.[rk]
              return (
                <div
                  key={rk}
                  className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2.5 text-center"
                >
                  <p className="text-xs text-zinc-500 mb-1">{t(`risk.${rk}`)}</p>
                  <p className="text-sm font-semibold text-zinc-100">
                    {rate == null ? '—' : `${pct(rate)}%`}
                  </p>
                  <p className="text-[10px] text-zinc-600 mt-0.5">{t('perMonthOfDeposit')}</p>
                </div>
              )
            })}
          </div>
          <p className="text-xs text-zinc-500 mt-2">{t('subscriptionNote')}</p>
        </section>

        {/* 成功報酬: tier（預け入れ規模）別 */}
        <section>
          <h3 className="text-sm font-semibold text-zinc-200 mb-2">{t('performanceTitle')}</h3>
          <div className="space-y-1.5">
            {TIER_KEYS.map((tk, i) => {
              const rate = config.tier_fee_rates?.[i]
              const lowerBound = i === 0 ? 0 : config.tier_thresholds_jpy?.[i - 1]
              const upperBound = config.tier_thresholds_jpy?.[i]
              const range =
                i === TIER_KEYS.length - 1
                  ? t('depositFrom', { amount: jpy(lowerBound ?? 0) })
                  : lowerBound === 0
                    ? t('depositUpTo', { amount: jpy(upperBound ?? 0) })
                    : t('depositRange', {
                        from: jpy(lowerBound ?? 0),
                        to: jpy(upperBound ?? 0),
                      })
              return (
                <div
                  key={tk}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2"
                >
                  <div>
                    <p className="text-sm text-zinc-200">{t(`tier.${tk}`)}</p>
                    <p className="text-[10px] text-zinc-600">{range}</p>
                  </div>
                  <p className="text-sm font-semibold text-zinc-100">
                    {rate == null ? '—' : `${pct(rate)}%`}
                  </p>
                </div>
              )
            })}
          </div>
          <p className="text-xs text-zinc-500 mt-2">{t('performanceNote')}</p>
        </section>

        {/* 課金タイミング + 現在無料の明示 */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2.5 space-y-1">
          <p className="text-xs text-zinc-400">{t('billingNote')}</p>
          <p className="text-xs text-amber-400/90">{t('notActiveNote')}</p>
        </div>
      </CardContent>
    </Card>
  )
}
