'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useCallback, useEffect, useRef, useState } from 'react'
import { Calculator, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import { apiPost } from '@/lib/api/client'
import { useTranslations } from 'next-intl'

// ---- Types ----

type RiskMode = 'conservative' | 'balanced' | 'aggressive'
type Tier = 'LOWER' | 'MIDDLE' | 'UPPER'

interface RiskModeOption {
  mode: RiskMode
  label: string
  allowed_in_phase_1: boolean
  subscription_rate: string
}

interface RiskModesResponse {
  modes: RiskModeOption[]
}

interface RiskModeCurrentResponse {
  mode: RiskMode
  label: string
}

interface SimulateRequest {
  deposit_jpy: number
  gross_profit_jpy: number
  expense_jpy: number
  user_tier: Tier
  user_risk_mode: RiskMode
  is_first_month: boolean
}

interface SimulateResult {
  net_profit_jpy: string
  fee_rate_applied: string
  fee_amount_jpy: string
  subscription_rate_applied: string
  subscription_amount_jpy: string
  subscription_protected: boolean
  monthly_yield_cap_applied: string
  yield_excess_to_uata_jpy: string
  user_takehome_jpy: string
}

interface FeeHistoryItem {
  calculation_month: string
  tier: string
  risk_mode: string
  deposit_jpy: string
  net_profit_jpy: string
  fee_amount_jpy: string
  subscription_amount_jpy: string
  user_takehome_jpy: string
}

// ---- Helpers ----

function computeTier(depositJpy: number): Tier {
  if (depositJpy <= 1_000_000) return 'LOWER'
  if (depositJpy <= 10_000_000) return 'MIDDLE'
  return 'UPPER'
}

const TIER_LABELS: Record<Tier, string> = {
  LOWER: 'ローワー (〜100万円)',
  MIDDLE: 'ミドル (〜1,000万円)',
  UPPER: 'アッパー (1,000万円〜)',
}

const RISK_MODE_LABELS: Record<RiskMode, string> = {
  conservative: 'ローリスク',
  balanced: 'ミドルリスク',
  aggressive: 'ハイリスク',
}

function fmtJpy(value: string | number): string {
  const n = typeof value === 'string' ? Number(value) : value
  if (isNaN(n)) return '¥—'
  return new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY', maximumFractionDigits: 0 }).format(n)
}

function fmtPct(value: string | number, digits = 2): string {
  const n = typeof value === 'string' ? Number(value) : value
  if (isNaN(n)) return '—%'
  return `${(n * 100).toFixed(digits)}%`
}

// ---- Fee History Table ----

function FeeHistorySection() {
  const t = useTranslations('FeeSimulator')
  const { data, loading } = useAuthFetch<FeeHistoryItem[]>('/api/v1/fees/my-history?limit=12')
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-4 pt-4 border-t border-zinc-800">
      <button
        className="flex items-center gap-1.5 text-sm font-medium text-zinc-300 hover:text-zinc-100 transition-colors w-full text-left"
        onClick={() => setOpen((v) => !v)}
        type="button"
        data-testid="fee-history-toggle"
      >
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        {t('historyTitle')}
      </button>

      {open && (
        <div className="mt-3">
          {loading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-8 rounded" />)}
            </div>
          ) : !data || data.length === 0 ? (
            <p className="text-sm text-zinc-500 text-center py-4">{t('historyEmpty')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800">
                    <th className="text-left py-2 px-2 text-zinc-500 font-medium">{t('historyMonth')}</th>
                    <th className="text-left py-2 px-2 text-zinc-500 font-medium">{t('historyTier')}</th>
                    <th className="text-right py-2 px-2 text-zinc-500 font-medium">{t('historyFee')}</th>
                    <th className="text-right py-2 px-2 text-zinc-500 font-medium">{t('historySub')}</th>
                    <th className="text-right py-2 px-2 text-zinc-500 font-medium">{t('historyTakehome')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((row, i) => (
                    <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="py-2 px-2 text-zinc-300">{row.calculation_month}</td>
                      <td className="py-2 px-2 text-zinc-400">{row.tier}</td>
                      <td className="py-2 px-2 text-right text-zinc-200">{fmtJpy(row.fee_amount_jpy)}</td>
                      <td className="py-2 px-2 text-right text-zinc-200">{fmtJpy(row.subscription_amount_jpy)}</td>
                      <td className="py-2 px-2 text-right text-emerald-400 font-medium">{fmtJpy(row.user_takehome_jpy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---- Simulator ----

function ResultRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-zinc-800/60 last:border-0">
      <span className="text-xs text-zinc-400">{label}</span>
      <span className={`text-sm font-semibold ${highlight ? 'text-emerald-400' : 'text-zinc-100'}`}>{value}</span>
    </div>
  )
}

// ---- Main Card ----

export function FeeSimulatorCard() {
  const t = useTranslations('FeeSimulator')
  const { data: currentMode } = useAuthFetch<RiskModeCurrentResponse>('/auth/risk-mode')
  const { data: modesData } = useAuthFetch<RiskModesResponse>('/auth/risk-modes')

  const [depositInput, setDepositInput] = useState('1000000')
  const [yieldRate, setYieldRate] = useState(3)
  const [isFirstMonth, setIsFirstMonth] = useState(false)
  const [result, setResult] = useState<SimulateResult | null>(null)
  const [simulating, setSimulating] = useState(false)
  const [simError, setSimError] = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const depositJpy = Math.max(0, Number(depositInput.replace(/[^0-9]/g, '')) || 0)
  const grossProfitJpy = Math.round(depositJpy * (yieldRate / 100))
  const tier = computeTier(depositJpy)
  const riskMode = currentMode?.mode ?? 'conservative'

  const runSimulate = useCallback(async (
    deposit: number,
    grossProfit: number,
    _tier: Tier,
    mode: RiskMode,
    firstMonth: boolean,
  ) => {
    if (deposit <= 0) {
      setResult(null)
      return
    }
    setSimulating(true)
    setSimError(false)
    try {
      const res = await apiPost<SimulateResult>('/api/v1/fees/simulate', {
        deposit_jpy: deposit,
        gross_profit_jpy: grossProfit,
        expense_jpy: 0,
        user_tier: _tier,
        user_risk_mode: mode,
        is_first_month: firstMonth,
      } satisfies SimulateRequest)
      setResult(res)
    } catch {
      setSimError(true)
      setResult(null)
    } finally {
      setSimulating(false)
    }
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      void runSimulate(depositJpy, grossProfitJpy, tier, riskMode, isFirstMonth)
    }, 500)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [depositJpy, grossProfitJpy, tier, riskMode, isFirstMonth, runSimulate])

  const subscriptionRate = modesData?.modes.find((m) => m.mode === riskMode)?.subscription_rate ?? '0'

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="fee-simulator-card">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Calculator className="h-4 w-4 text-zinc-400" />
          <CardTitle className="text-base text-zinc-100">{t('title')}</CardTitle>
        </div>
        <p className="text-xs text-zinc-500">{t('subtitle')}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Inputs */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {/* 運用資産額 */}
          <div className="space-y-1.5">
            <label className="text-xs text-zinc-400">{t('depositLabel')}</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-zinc-500">¥</span>
              <input
                type="number"
                min={0}
                step={100000}
                value={depositInput}
                onChange={(e) => setDepositInput(e.target.value)}
                data-testid="fee-simulator-deposit"
                className="w-full rounded-md border border-zinc-700 bg-zinc-800 pl-6 pr-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
                placeholder="1000000"
              />
            </div>
            {depositJpy > 0 && (
              <p className="text-[10px] text-zinc-500">
                {t('tierLabel')}: <span className="text-zinc-300">{TIER_LABELS[tier]}</span>
              </p>
            )}
          </div>

          {/* 想定月利率 */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs text-zinc-400">{t('yieldLabel')}</label>
              <span className="text-xs font-semibold text-zinc-200" data-testid="fee-simulator-yield-display">
                {yieldRate.toFixed(1)}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={20}
              step={0.5}
              value={yieldRate}
              onChange={(e) => setYieldRate(Number(e.target.value))}
              data-testid="fee-simulator-yield"
              className="w-full accent-emerald-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-zinc-600">
              <span>0%</span>
              <span>10%</span>
              <span>20%</span>
            </div>
          </div>
        </div>

        {/* Info row */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-zinc-500">{t('riskModeLabel')}:</span>
          <Badge variant="outline" className="text-[11px] border-zinc-700 text-zinc-300 py-0">
            {RISK_MODE_LABELS[riskMode]}
          </Badge>
          {Number(subscriptionRate) > 0 && (
            <span className="text-zinc-500">
              {t('subscriptionFee')}: {fmtPct(subscriptionRate)}/月
            </span>
          )}
          <label className="flex items-center gap-1 ml-auto cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isFirstMonth}
              onChange={(e) => setIsFirstMonth(e.target.checked)}
              data-testid="fee-simulator-first-month"
              className="rounded accent-emerald-500"
            />
            <span className="text-zinc-400">{t('firstMonthFree')}</span>
          </label>
        </div>

        {/* Results */}
        {depositJpy > 0 && (
          <div className="rounded-lg bg-zinc-800/50 border border-zinc-700/50 px-4 py-3" data-testid="fee-simulator-result">
            <p className="text-xs font-semibold text-zinc-400 mb-2">{t('resultTitle')}</p>

            {simulating ? (
              <div className="space-y-2">
                {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-6 rounded" />)}
              </div>
            ) : simError ? (
              <p className="text-xs text-zinc-500 text-center py-2">{t('simulateError')}</p>
            ) : result ? (
              <div>
                <ResultRow label={t('grossProfit')} value={fmtJpy(grossProfitJpy)} />
                <ResultRow label={t('netProfit')} value={fmtJpy(result.net_profit_jpy)} />
                <ResultRow
                  label={`${t('subscriptionFee')} (${fmtPct(result.subscription_rate_applied)})`}
                  value={`-${fmtJpy(result.subscription_amount_jpy)}`}
                />
                <ResultRow
                  label={`${t('performanceFee')} (${fmtPct(result.fee_rate_applied)})`}
                  value={`-${fmtJpy(result.fee_amount_jpy)}`}
                />
                {Number(result.yield_excess_to_uata_jpy) > 0 && (
                  <ResultRow
                    label={t('uataShare')}
                    value={`-${fmtJpy(result.yield_excess_to_uata_jpy)}`}
                  />
                )}
                <ResultRow label={t('userTakehome')} value={fmtJpy(result.user_takehome_jpy)} highlight />
              </div>
            ) : null}
          </div>
        )}

        {/* History (collapsible) */}
        <FeeHistorySection />
      </CardContent>
    </Card>
  )
}
