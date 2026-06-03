// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

interface FeeConfigResponse {
  config_name: string
  tier_thresholds_jpy: number[]
  tier_fee_rates: number[]
  tier_monthly_yield_caps: number[]
  subscription_rates: Record<string, number>
  expense_markup_enabled: boolean
  expense_markup_rate: string
  affiliate_rate: string
  is_active: boolean
  effective_from: string
}

const TIER_LABELS = ['LOWER', 'MIDDLE', 'UPPER']

function pct(v: number) {
  return `${(v * 100).toFixed(2)}%`
}

function jpy(v: number) {
  return `¥${v.toLocaleString()}`
}

export function FeeConfigCard() {
  const [config, setConfig] = useState<FeeConfigResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<FeeConfigResponse>('/api/v1/fees/config')
      .then((data) => setConfig(data))
      .catch(() => setError('取得に失敗しました'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <CardTitle className="text-base text-zinc-100">手数料設定 (Fee Model v10)</CardTitle>
          {config?.is_active && (
            <Badge className="bg-emerald-600 text-white text-xs">Active</Badge>
          )}
        </div>
        {config && (
          <p className="text-xs text-zinc-500 mt-1">
            {config.config_name} — 有効開始: {new Date(config.effective_from).toLocaleDateString('ja-JP')}
          </p>
        )}
      </CardHeader>
      <CardContent>
        {loading && (
          <p className="text-sm text-zinc-500">読み込み中...</p>
        )}
        {error && (
          <p className="text-sm text-red-400">{error}</p>
        )}
        {config && (
          <div className="space-y-5">
            {/* Tier 手数料・利回り上限 */}
            <div>
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">
                Tier 別 手数料率 / 月次利回り上限
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                      <th className="text-left py-1.5 pr-4">Tier</th>
                      <th className="text-left py-1.5 pr-4">デポジット下限</th>
                      <th className="text-right py-1.5 pr-4">手数料率</th>
                      <th className="text-right py-1.5">月次利回り上限</th>
                    </tr>
                  </thead>
                  <tbody>
                    {TIER_LABELS.map((label, i) => (
                      <tr key={label} className="border-b border-zinc-800/50">
                        <td className="py-2 pr-4 text-zinc-100 font-medium">{label}</td>
                        <td className="py-2 pr-4 text-zinc-300">
                          {i === 0
                            ? '—'
                            : jpy(config.tier_thresholds_jpy[i - 1] ?? 0)}
                        </td>
                        <td className="py-2 pr-4 text-right text-zinc-300">
                          {pct(config.tier_fee_rates[i] ?? 0)}
                        </td>
                        <td className="py-2 text-right text-zinc-300">
                          {pct(config.tier_monthly_yield_caps[i] ?? 0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* サブスクリプション率 */}
            <div>
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">
                サブスクリプション率
              </h3>
              <div className="grid grid-cols-3 gap-2">
                {Object.entries(config.subscription_rates).map(([tier, rate]) => (
                  <div key={tier} className="rounded-lg bg-zinc-800/60 px-3 py-2">
                    <p className="text-xs text-zinc-500">{tier}</p>
                    <p className="text-sm font-medium text-zinc-100 mt-0.5">{pct(rate)}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* 経費マークアップ / 紹介キャンペーン */}
            <div>
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">
                その他レート
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-zinc-800/60 px-3 py-2">
                  <p className="text-xs text-zinc-500">経費マークアップ</p>
                  <p className="text-sm font-medium text-zinc-100 mt-0.5">
                    {config.expense_markup_enabled
                      ? `${(Number(config.expense_markup_rate) * 100).toFixed(1)}%`
                      : '無効'}
                  </p>
                </div>
                <div className="rounded-lg bg-zinc-800/60 px-3 py-2">
                  <p className="text-xs text-zinc-500">紹介キャンペーン報酬率</p>
                  <p className="text-sm font-medium text-zinc-100 mt-0.5">
                    {`${(Number(config.affiliate_rate) * 100).toFixed(1)}%`}
                  </p>
                </div>
              </div>
            </div>

            <p className="text-xs text-zinc-600">
              * 設定変更は DB 直接 + スクリプト再投入が必要です（UI 書き込み非対応 / Phase 1）
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
