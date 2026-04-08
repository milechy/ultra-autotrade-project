'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { Clock, CheckCircle, XCircle, Timer } from 'lucide-react'
import { KPICard } from '@/components/shared/KPICard'
import { useAuth } from '@/lib/auth'
import { fetchAdminProposalStats } from '@/lib/api/admin-proposals'
import type { AdminProposalStats } from '@/lib/api/admin-proposals'

export function ProposalKPIs() {
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
      <KPICard label="承認待ち" value={pending} suffix="件" icon={Clock} />
      <KPICard label="本日承認" value={todayApproved} suffix="件" icon={CheckCircle} />
      <KPICard label="本日拒否" value={todayRejected} suffix="件" icon={XCircle} />
      <KPICard label="タイムアウト" value={expired} suffix="件" icon={Timer} />
    </div>
  )
}
