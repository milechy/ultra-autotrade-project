'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  PortfolioSummary,
  PositionList,
  AssetChart,
  LatestDecision,
  SafetyScore,
} from './_components'
import { apiFetch } from '@/lib/api/client'

// ---- Types ----

type UserMode = 'managed' | 'active' | 'pro'
type RiskMode = 'conservative' | 'balanced' | 'aggressive'

interface UserSettings {
  user_mode: UserMode
  execution_policy?: string
}

interface RiskModeData {
  mode: RiskMode
}

const RISK_MODE_CLASS: Record<RiskMode, string> = {
  conservative: 'border-emerald-500/50 bg-emerald-950/30 text-emerald-400',
  balanced: 'border-blue-500/50 bg-blue-950/30 text-blue-400',
  aggressive: 'border-orange-500/50 bg-orange-950/30 text-orange-400',
}

// ---- RiskModeBadge ----

function RiskModeBadge() {
  const [riskMode, setRiskMode] = useState<RiskMode | null>(null)
  const t = useTranslations('riskMode')

  useEffect(() => {
    apiFetch<RiskModeData>('/auth/risk-mode')
      .then((data) => setRiskMode(data.mode))
      .catch(() => {/* silently ignore */})
  }, [])

  if (!riskMode) return null

  return (
    <Badge
      variant="outline"
      className={RISK_MODE_CLASS[riskMode]}
    >
      {t(`badge.${riskMode}`)}
    </Badge>
  )
}

interface Transaction {
  operation: string
  asset: string
  amount_usd: string
  created_at: string
  status: string
}

interface TransactionsResponse {
  items: Transaction[]
}

// ---- ManagedDashboard ----

function RecentOpsCard() {
  const [items, setItems] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [hasError, setHasError] = useState(false)
  const t = useTranslations('Dashboard')

  useEffect(() => {
    apiFetch<TransactionsResponse>('/api/transactions?limit=5')
      .then((res) => setItems(res.items ?? []))
      .catch(() => setHasError(true))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-zinc-500" />
        <h2 className="text-sm font-semibold text-zinc-400">{t('recentOps')}</h2>
      </div>

      {loading && (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-10 rounded-lg" />
          ))}
        </div>
      )}

      {!loading && (hasError || items.length === 0) && (
        <p className="text-sm text-zinc-500 py-4 text-center">{t('noOpsHistory')}</p>
      )}

      {!loading && !hasError && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((tx, i) => (
            <li
              key={i}
              className="flex items-center justify-between rounded-lg bg-zinc-800/60 px-3 py-2"
            >
              <div className="space-y-0.5">
                <p className="text-xs font-medium text-zinc-200">
                  {tx.operation} — {tx.asset}
                </p>
                <p className="text-xs text-zinc-500">
                  {new Date(tx.created_at).toLocaleDateString('ja-JP', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
              <div className="text-right space-y-0.5">
                <p className="text-xs font-semibold text-zinc-100">${tx.amount_usd}</p>
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    tx.status === 'success'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : tx.status === 'failed'
                      ? 'bg-red-500/20 text-red-400'
                      : 'bg-zinc-700 text-zinc-400'
                  }`}
                >
                  {tx.status}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ManagedDashboard() {
  const t = useTranslations('Dashboard')
  return (
    <div className="px-4 py-6 max-w-4xl mx-auto space-y-6">
      {/* AI running badge + Risk mode badge */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-800 bg-emerald-950/40 px-4 py-3">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-sm font-semibold text-emerald-400">{t('aiRunning')}</span>
        </div>
        <RiskModeBadge />
      </div>

      {/* Portfolio KPIs */}
      <section>
        <PortfolioSummary />
      </section>

      {/* Safety Score */}
      <section>
        <SafetyScore />
      </section>

      {/* Recent ops */}
      <section>
        <RecentOpsCard />
      </section>

      {/* Footer note */}
      <p className="text-center text-xs text-zinc-600">
        {t('managedFootnote')}
      </p>
    </div>
  )
}

// ---- Full (active / pro) Dashboard ----

function ActiveDashboard() {
  const t = useTranslations('Dashboard')
  return (
    <div className="px-4 py-6 max-w-4xl mx-auto space-y-6">
      {/* Risk mode badge */}
      <div className="flex items-center gap-2">
        <RiskModeBadge />
      </div>

      <section>
        <PortfolioSummary />
      </section>

      <section>
        <SafetyScore />
      </section>

      <section>
        <h2 className="text-sm font-semibold text-zinc-400 mb-3">{t('positions')}</h2>
        <PositionList />
      </section>

      <section>
        <h2 className="text-sm font-semibold text-zinc-400 mb-3">{t('assetChart')}</h2>
        <AssetChart />
      </section>

      <section>
        <h2 className="text-sm font-semibold text-zinc-400 mb-3">{t('latestDecision')}</h2>
        <LatestDecision />
      </section>
    </div>
  )
}

// ---- Page ----

export default function DashboardPage() {
  const [userMode, setUserMode] = useState<UserMode | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    apiFetch<UserSettings>('/api/user/settings')
      .then((res) => setUserMode(res.user_mode ?? 'active'))
      .catch(() => {
        setLoadError(true)
        setUserMode('active') // fallback to full dashboard on error
      })
  }, [])

  // Loading skeleton
  if (userMode === null && !loadError) {
    return (
      <div className="px-4 py-6 max-w-4xl mx-auto space-y-4">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-36 rounded-xl" />
        <Skeleton className="h-20 rounded-xl" />
      </div>
    )
  }

  if (userMode === 'managed') {
    return <ManagedDashboard />
  }

  return <ActiveDashboard />
}
