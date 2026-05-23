'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { apiFetch } from '@/lib/api/client'
import { useAuth } from '@/lib/auth'
import { logUserAction } from '@/lib/api/user_actions'
import { EmptyStateWithAIStatus } from '@/components/approve/EmptyStateWithAIStatus'
import {
  ProposalCard,
  RecentApprovals,
  ProposalStatus,
  Proposal,
  RecentApproval,
} from './_components'

interface ProposalAPIResponse {
  id: number
  user_id: number
  operation: string
  asset: string
  amount: string
  amount_usd: string
  reason: string
  expected_hf_after: string | null
  estimated_gas_usd: string | null
  status: string
  tx_hash: string | null
  expires_at: string
  created_at: string
}

interface ProposalListResponse {
  items: ProposalAPIResponse[]
  total: number
}

function mapToProposal(item: ProposalAPIResponse): Proposal {
  return {
    id: String(item.id),
    operation: item.operation as Proposal['operation'],
    asset: item.asset,
    amount: parseFloat(item.amount),
    amountUSD: parseFloat(item.amount_usd),
    reason: item.reason,
    currentHF: 0,
    projectedHF: item.expected_hf_after ? parseFloat(item.expected_hf_after) : 0,
    estimatedGas: item.estimated_gas_usd ? parseFloat(item.estimated_gas_usd) : 0,
    slippage: null,
    createdAt: item.created_at,
  }
}

function mapToRecentApproval(item: ProposalAPIResponse): RecentApproval {
  return {
    id: String(item.id),
    operation: item.operation as RecentApproval['operation'],
    asset: item.asset,
    amount: parseFloat(item.amount),
    status: item.status === 'executed' ? 'success' : item.status === 'rejected' ? 'failed' : 'success',
    txHash: item.tx_hash ?? '',
    timestamp: item.created_at,
  }
}

type ProposalState = {
  status: ProposalStatus
  txHash?: string
}

export default function ApprovePage() {
  const { isAuthenticated, isLoading: authLoading, isPartner } = useAuth()
  const router = useRouter()
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [recentApprovals, setRecentApprovals] = useState<RecentApproval[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [proposalStates, setProposalStates] = useState<
    Record<string, ProposalState>
  >({})

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [pendingRes, historyRes] = await Promise.all([
        apiFetch<ProposalListResponse>('/api/proposals/pending'),
        apiFetch<ProposalListResponse>('/api/proposals/history?limit=5'),
      ])
      setProposals(pendingRes.items.map(mapToProposal))
      setRecentApprovals(historyRes.items.map(mapToRecentApproval))
    } catch {
      setError('データを取得できません')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.replace('/login?redirect=/user/approve')
    } else if (!authLoading && isAuthenticated && !isPartner) {
      router.replace('/user/dashboard')
    }
  }, [authLoading, isAuthenticated, isPartner, router])

  useEffect(() => {
    if (isAuthenticated) { fetchData() }
  }, [fetchData, isAuthenticated])

  // ⚠️ P5 display-only: 本ハンドラは「実取引 API」を呼びません。
  // 本機能は機能説明用 (manual UI is display-only) です。
  // 実取引は AI スケジューラが全自動で実行します (main.py / ai_judgment_scheduler.py)。
  // クリックは user_actions ログにのみ記録し、proposal 一覧の見た目だけ更新します。
  //
  // ※ 旧実装: apiPost(`/api/proposals/${id}/approve`) を直接呼んでいた箇所を撤去。
  //   今後 manual 取引 API を再有効化する場合も、法務 sign-off と
  //   AI スケジューラ停止フラグの整合確認を経た上で別 PR で行うこと。
  const handleApprove = useCallback(async (id: string) => {
    console.log('[manual-ui] display-only approve click', { proposal_id: id })
    setProposalStates((prev) => ({ ...prev, [id]: { status: 'approving' } }))
    // best-effort log; never blocks UI even if backend endpoint is pending
    void logUserAction({
      action_type: 'manual_approve_click',
      target_type: 'proposal',
      target_id: id,
    })
    // visually mark as "received" without performing a real on-chain action
    setTimeout(() => {
      setProposalStates((prev) => ({
        ...prev,
        [id]: { status: 'success' },
      }))
    }, 300)
    setTimeout(() => {
      setProposals((prev) => prev.filter((p) => p.id !== id))
    }, 2000)
  }, [])

  const handleReject = useCallback(async (id: string) => {
    console.log('[manual-ui] display-only reject click', { proposal_id: id })
    void logUserAction({
      action_type: 'manual_reject_click',
      target_type: 'proposal',
      target_id: id,
    })
    setProposals((prev) => prev.filter((p) => p.id !== id))
    setProposalStates((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const pendingCount = proposals.filter((p) => {
    const s = proposalStates[p.id]?.status ?? 'pending'
    return s === 'pending' || s === 'approving' || s === 'confirming'
  }).length

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-48 rounded-xl" />
          <Skeleton className="h-48 rounded-xl" />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold">取引承認</h1>
              {pendingCount > 0 && (
                <Badge className="bg-orange-500 hover:bg-orange-500 text-white text-xs px-2 py-0.5">
                  {pendingCount}件待ち
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              AIが提案した取引を確認・承認してください
            </p>
            {/* P5 display-only label: 法務 sign-off 後に文言は最終化 */}
            <small className="block text-muted-foreground mt-1">
              本機能は機能説明用です。実取引は全自動で実行されます。
            </small>
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="rounded-lg border border-red-800 bg-red-950 p-3">
            <p className="text-sm text-red-400">{error}</p>
            <button onClick={fetchData} className="text-xs text-blue-400 underline mt-1">再試行</button>
          </div>
        )}

        {/* Proposal list */}
        {proposals.length === 0 ? (
          <EmptyStateWithAIStatus />
        ) : (
          <div className="space-y-4">
            {proposals.map((proposal) => {
              const state = proposalStates[proposal.id] ?? { status: 'pending' as ProposalStatus }
              return (
                <ProposalCard
                  key={proposal.id}
                  proposal={proposal}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  status={state.status}
                  txHash={state.txHash}
                />
              )
            })}
          </div>
        )}

        {/* Recent approvals */}
        <RecentApprovals approvals={recentApprovals} />
      </div>
    </div>
  )
}
