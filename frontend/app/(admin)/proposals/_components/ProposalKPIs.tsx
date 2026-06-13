'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { Clock, CheckCircle, XCircle, Timer } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { KPICard } from '@/components/shared/KPICard'
import { useAuth } from '@/lib/auth'
import { fetchAdminProposalStats } from '@/lib/api/admin-proposals'
import type { AdminProposalStats } from '@/lib/api/admin-proposals'

export function ProposalKPIs() {
  const t = useTranslations('AdminProposalKPIs')
  const { token } = useAuth()
  const [stats, setStats] = useState<AdminProposalStats | null>(null)

  useEffect(() => {
    if (!token) return
    fetchAdminProposalStats(token)
      .then(setStats)
      .catch(() => {
        // サイレントフェイル — メインのエラーバナーがある
      })
  }, [token])

  const pending = stats?.pending ?? 0
  const todayApproved = stats?.today_approved ?? 0
  const todayRejected = stats?.today_rejected ?? 0
  const expired = stats?.expired ?? 0

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <KPICard label={t('pending')} value={pending} suffix={t('countSuffix')} icon={Clock} />
      <KPICard label={t('todayApproved')} value={todayApproved} suffix={t('countSuffix')} icon={CheckCircle} />
      <KPICard label={t('todayRejected')} value={todayRejected} suffix={t('countSuffix')} icon={XCircle} />
      <KPICard label={t('timeout')} value={expired} suffix={t('countSuffix')} icon={Timer} />
    </div>
  )
}
