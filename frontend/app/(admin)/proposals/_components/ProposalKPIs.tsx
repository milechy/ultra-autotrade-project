'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { Clock, CheckCircle, XCircle, Timer } from 'lucide-react'
import { KPICard } from '@/components/shared/KPICard'
import type { AdminProposal } from '@/lib/api/admin-proposals'

interface ProposalKPIsProps {
  proposals: AdminProposal[]
}

export function ProposalKPIs({ proposals }: ProposalKPIsProps) {
  const today = new Date().toDateString()

  const pendingCount = proposals.filter((p) => p.status === 'pending').length
  const todayApproved = proposals.filter(
    (p) =>
      (p.status === 'approved' || p.status === 'executed') &&
      p.approved_at &&
      new Date(p.approved_at).toDateString() === today
  ).length
  const todayRejected = proposals.filter(
    (p) =>
      p.status === 'rejected' &&
      p.rejected_at &&
      new Date(p.rejected_at).toDateString() === today
  ).length
  const expiredCount = proposals.filter((p) => p.status === 'expired').length

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <KPICard label="承認待ち" value={pendingCount} suffix="件" icon={Clock} />
      <KPICard label="本日承認" value={todayApproved} suffix="件" icon={CheckCircle} />
      <KPICard label="本日拒否" value={todayRejected} suffix="件" icon={XCircle} />
      <KPICard label="タイムアウト" value={expiredCount} suffix="件" icon={Timer} />
    </div>
  )
}
