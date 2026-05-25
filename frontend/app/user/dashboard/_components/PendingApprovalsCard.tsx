'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { CheckCircle, ChevronRight } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuthFetch } from '@/hooks/useAuthFetch'

interface ProposalItem {
  id: number
  operation: string
  asset: string
  amount_usd: string
  expires_at: string
}

interface ProposalListResponse {
  items: ProposalItem[]
  total: number
}

/**
 * 承認待ち proposal の件数を dashboard に表示する。
 *
 * Lane の前回 UAT 導線調査: dashboard が /api/proposals/pending を引いておらず、
 * viewer が承認画面に行く動機を失っていた。本カードで件数 + 直近1件を提示し、
 * `/user/approve` への遷移導線を提示する。
 *
 * RBAC: backend 側で本人 user_id でフィルタするので、role に依らず安全に呼べる。
 */
export function PendingApprovalsCard() {
  const t = useTranslations('Dashboard')
  // 30秒ポーリング — 承認は時間に敏感だが頻度すぎると user の clock が走り過ぎる
  const { data, loading } = useAuthFetch<ProposalListResponse>(
    '/api/proposals/pending',
    { refreshInterval: 30000 },
  )

  if (loading && !data) {
    return <Skeleton className="h-28 rounded-2xl" />
  }

  const items = data?.items ?? []
  const total = data?.total ?? items.length
  const next = items[0]

  return (
    <Link
      href="/user/approve"
      className="block rounded-2xl border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-blue-500/50 hover:bg-zinc-900/70"
      aria-label={t('pendingApprovalsAria', { count: total })}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <CheckCircle
            className={`h-4 w-4 ${total > 0 ? 'text-blue-400' : 'text-zinc-500'}`}
          />
          <h2 className="text-sm font-semibold text-zinc-400">
            {t('pendingApprovals')}
          </h2>
        </div>

        <div className="flex items-center gap-2">
          {total > 0 && (
            <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-xs font-bold text-blue-400">
              {total > 99 ? '99+' : total}
            </span>
          )}
          <ChevronRight className="h-4 w-4 text-zinc-600" />
        </div>
      </div>

      <p className="mt-3 text-sm text-zinc-300">
        {total === 0
          ? t('noPendingApprovals')
          : t('pendingApprovalsCount', { count: total })}
      </p>

      {next && (
        <p className="mt-1 text-xs text-zinc-500">
          {t('pendingApprovalsNext', {
            operation: next.operation,
            asset: next.asset,
            amount: Number(next.amount_usd).toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            }),
          })}
        </p>
      )}
    </Link>
  )
}
