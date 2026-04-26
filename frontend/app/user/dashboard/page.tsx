'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { Clock, Wallet } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  PortfolioSummary,
  PositionList,
  AssetChart,
  LatestDecision,
  SafetyScore,
  AiAccuracyCard,
  RiskModeSelectorCard,
} from './_components'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import { useAuth } from '@/lib/auth'

// Note: PortfolioSummary, SafetyScore, AiAccuracyCard are used by ActiveDashboard only

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
  const { data } = useAuthFetch<RiskModeData>('/auth/risk-mode')
  const riskMode = data?.mode ?? null
  const t = useTranslations('riskMode')

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

// ---- AllocationCard ----

interface MyAllocation {
  allocated_amount_usd: string
  partner_name: string
  status: string
  allocated_at: string
  pnl_usd: string | null
  pnl_percentage: string | null
}

function AllocationCard() {
  const { data, loading } = useAuthFetch<MyAllocation | null>('/api/user/my-allocation', { refreshInterval: 300000 })
  const t = useTranslations('Dashboard')

  if (loading) {
    return <Skeleton className="h-28 rounded-2xl" />
  }

  const statusLabel = data?.status === 'active' ? t('allocationActive') : data?.status === 'withdrawn' ? t('allocationWithdrawn') : data?.status ?? ''
  const pnlPositive = data?.pnl_usd != null && Number(data.pnl_usd) >= 0

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Wallet className="h-4 w-4 text-zinc-500" />
        <h2 className="text-sm font-semibold text-zinc-400">{t('myAllocation')}</h2>
      </div>

      {data == null ? (
        <p className="text-sm text-zinc-500 py-2 text-center">{t('noAllocation')}</p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
          <div>
            <dt className="text-xs text-zinc-500">{t('allocatedAmount')}</dt>
            <dd className="text-sm font-semibold text-zinc-100">
              ${Number(data.allocated_amount_usd).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </dd>
          </div>

          <div>
            <dt className="text-xs text-zinc-500">{t('partnerName')}</dt>
            <dd className="text-sm font-semibold text-zinc-100">{data.partner_name}</dd>
          </div>

          <div>
            <dt className="text-xs text-zinc-500">{t('allocationStatus')}</dt>
            <dd>
              <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${
                data.status === 'active'
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-zinc-700 text-zinc-400'
              }`}>
                {statusLabel}
              </span>
            </dd>
          </div>

          {data.pnl_usd != null && (
            <div>
              <dt className="text-xs text-zinc-500">{t('allocationPnl')}</dt>
              <dd className={`text-sm font-semibold ${pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                {pnlPositive ? '+' : ''}${Number(data.pnl_usd).toFixed(2)}
                {data.pnl_percentage != null && (
                  <span className="ml-1 text-xs">
                    ({pnlPositive ? '+' : ''}{Number(data.pnl_percentage).toFixed(2)}%)
                  </span>
                )}
              </dd>
            </div>
          )}
        </dl>
      )}
    </div>
  )
}

// ---- ManagedDashboard ----

function RecentOpsCard() {
  const { data, loading, error: fetchError } = useAuthFetch<TransactionsResponse>('/api/transactions?limit=5')
  const items = data?.items ?? []
  const t = useTranslations('Dashboard')

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

      {!loading && (fetchError || items.length === 0) && (
        <p className="text-sm text-zinc-500 py-4 text-center">{t('noOpsHistory')}</p>
      )}

      {!loading && !fetchError && items.length > 0 && (
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
  const { isAdmin, isPartner } = useAuth()
  const canSelectRiskMode = isAdmin || isPartner

  return (
    <div className="px-4 py-6 max-w-4xl mx-auto space-y-6">
      {/* リスクモード選択 (admin/partner のみ) */}
      {canSelectRiskMode && (
        <section>
          <RiskModeSelectorCard />
        </section>
      )}

      {/* 資金割り振り — メインコンテンツ */}
      <section>
        <AllocationCard />
      </section>

      {/* 最近の自動運用 */}
      <section>
        <RecentOpsCard />
      </section>
    </div>
  )
}

// ---- Full (active / pro) Dashboard ----

function ActiveDashboard() {
  const t = useTranslations('Dashboard')
  const { isAdmin, isPartner } = useAuth()
  const canSelectRiskMode = isAdmin || isPartner

  return (
    <div className="px-4 py-6 max-w-4xl mx-auto space-y-6">
      {/* Risk mode badge (all users) */}
      <div className="flex items-center gap-2">
        <RiskModeBadge />
      </div>

      {/* リスクモード選択カード (admin/partner のみ) */}
      {canSelectRiskMode && (
        <section>
          <RiskModeSelectorCard />
        </section>
      )}

      <section>
        <PortfolioSummary />
      </section>

      <section>
        <SafetyScore />
      </section>

      <section>
        <AllocationCard />
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

      <section>
        <AiAccuracyCard />
      </section>

      {/* Disclaimer */}
      <p className="text-center text-xs text-zinc-600">
        ※参考利回りです。将来の収益を保証するものではありません
      </p>
    </div>
  )
}

// ---- Page ----

export default function DashboardPage() {
  const { data: settings, error: settingsError } = useAuthFetch<UserSettings>('/api/user/settings')
  // Resolve to 'active' as soon as any response arrives (data or error).
  // Keeps null only during the initial loading state (no response yet).
  const userMode: UserMode | null =
    settings?.user_mode ?? (settings !== null || settingsError !== null ? 'active' : null)

  // Loading skeleton
  if (userMode === null) {
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
