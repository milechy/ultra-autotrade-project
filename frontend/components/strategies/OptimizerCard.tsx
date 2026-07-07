// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/strategies/OptimizerCard.tsx
//
// AI Optimizer 戦略推奨カード（監査 G1 / 1215915078947015）。
// 投資額・リスクモード・保有日数を入力して POST /api/ai/optimizer/recommend を呼び、
// 推奨戦略 + 最適配分を表示する。backend 実装済み・本カードで UI 配線して価値露出する。
'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Sparkles } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  recommendStrategy,
  type OptimizerResponse,
  type RiskMode,
  type RecommendationLevel,
} from '@/lib/api/optimizer'

const RISK_MODES: RiskMode[] = ['conservative', 'balanced', 'aggressive']

// Decimal 文字列 → 表示用数値（NaN は 0 にフォールバック）
function num(v: string | number | null | undefined): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function recommendationColor(level: RecommendationLevel): string {
  switch (level) {
    case 'STRONG_BUY':
      return 'border-green-500/30 bg-green-500/20 text-green-400'
    case 'BUY':
      return 'border-emerald-500/30 bg-emerald-500/20 text-emerald-400'
    case 'HOLD':
      return 'border-yellow-500/30 bg-yellow-500/20 text-yellow-400'
    case 'AVOID':
      return 'border-red-500/30 bg-red-500/20 text-red-400'
  }
}

export function OptimizerCard() {
  const t = useTranslations('Strategies.optimizer')

  const [investment, setInvestment] = useState('1000')
  const [riskMode, setRiskMode] = useState<RiskMode>('conservative')
  const [holdingDays, setHoldingDays] = useState('30')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<OptimizerResponse | null>(null)

  const investmentNum = num(investment)
  const holdingNum = num(holdingDays)
  const canSubmit = investmentNum > 0 && holdingNum > 0 && !loading

  // protocol enum → 表示ラベル（i18n。未知値はそのまま表示）
  function protocolLabel(p: string): string {
    const known = ['aave', 'lido', 'lido_aave', 'pendle_pt', 'pendle_yt', 'idle']
    return known.includes(p) ? t(`protocol.${p}`) : p
  }

  async function handleSubmit() {
    if (!canSubmit) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await recommendStrategy({
        investment_usd: investmentNum,
        risk_mode: riskMode,
        holding_days: Math.round(holdingNum),
      })
      setResult(res)
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? String(e)
      setError(msg || t('error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="border-zinc-800 bg-zinc-900" data-testid="optimizer-card">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <div className="rounded-lg border border-zinc-700 bg-zinc-800 p-2">
            <Sparkles className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <CardTitle className="text-base text-zinc-100">{t('title')}</CardTitle>
            <p className="text-xs text-zinc-500 mt-0.5">{t('subtitle')}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 入力 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="opt-investment" className="text-xs text-zinc-400">
              {t('investmentLabel')}
            </Label>
            <Input
              id="opt-investment"
              type="number"
              inputMode="decimal"
              min={0}
              value={investment}
              onChange={(e) => setInvestment(e.target.value)}
              className="bg-zinc-800 border-zinc-700 text-zinc-100"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="opt-days" className="text-xs text-zinc-400">
              {t('holdingDaysLabel')}
            </Label>
            <Input
              id="opt-days"
              type="number"
              inputMode="numeric"
              min={1}
              value={holdingDays}
              onChange={(e) => setHoldingDays(e.target.value)}
              className="bg-zinc-800 border-zinc-700 text-zinc-100"
            />
          </div>
        </div>

        {/* リスクモード */}
        <div className="space-y-1">
          <Label className="text-xs text-zinc-400">{t('riskModeLabel')}</Label>
          <div className="grid grid-cols-3 gap-2">
            {RISK_MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                data-testid={`optimizer-risk-${mode}`}
                onClick={() => setRiskMode(mode)}
                className={`rounded-md border px-2 py-1.5 text-xs transition-colors ${
                  riskMode === mode
                    ? 'border-blue-500/50 bg-blue-500/20 text-blue-300'
                    : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                }`}
              >
                {t(`riskMode.${mode}`)}
              </button>
            ))}
          </div>
        </div>

        <Button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="w-full"
          data-testid="optimizer-submit"
        >
          {loading ? t('calculating') : t('submit')}
        </Button>

        {error && (
          <p className="text-xs text-red-400" data-testid="optimizer-error">
            {t('error')}: {error}
          </p>
        )}

        {/* 結果 */}
        {result && (
          <div className="space-y-4 pt-2" data-testid="optimizer-result">
            {/* 推奨戦略 */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="text-xs text-zinc-500">{t('recommendedLabel')}</p>
                  <p className="text-sm font-semibold text-zinc-100">
                    {protocolLabel(result.comparison.recommended.protocol)}（
                    {result.comparison.recommended.asset}）
                  </p>
                </div>
                <Badge className={recommendationColor(result.comparison.recommended.recommendation)}>
                  {num(result.comparison.recommended.expected_apy).toFixed(2)}% APY
                </Badge>
              </div>
            </div>

            {/* 配分テーブル */}
            <div>
              <p className="text-xs text-zinc-500 mb-2">{t('allocationLabel')}</p>
              <div className="space-y-1.5">
                {result.allocation.allocations.map((a, i) => (
                  <div
                    key={`${a.protocol}-${a.asset}-${i}`}
                    className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-800/40 px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-zinc-200">{protocolLabel(a.protocol)}</span>
                      <span className="text-xs text-zinc-500">{a.asset}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-zinc-300">{num(a.allocation_pct).toFixed(1)}%</span>
                      <span className="text-zinc-500">
                        ${num(a.amount_usd).toFixed(2)}
                      </span>
                      <span className="text-blue-400">{num(a.expected_apy).toFixed(2)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 合計 + 説明 */}
            <div className="flex items-center gap-4">
              <div>
                <p className="text-xs text-zinc-500">{t('totalApyLabel')}</p>
                <p className="text-sm font-semibold text-zinc-100">
                  {num(result.allocation.total_expected_apy).toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">{t('riskScoreLabel')}</p>
                <p className="text-sm font-semibold text-zinc-100">
                  {num(result.allocation.total_risk_score).toFixed(2)}
                </p>
              </div>
            </div>

            {result.allocation.explanation && (
              <p className="text-xs text-zinc-400 leading-relaxed">
                {result.allocation.explanation}
              </p>
            )}

            <p className="text-[10px] text-zinc-600">{t('disclaimer')}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
