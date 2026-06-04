'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { apiFetch, apiPost } from '@/lib/api/client'
import { useAuth } from '@/lib/auth'
import { EmptyStateWithAIStatus } from '@/components/approve/EmptyStateWithAIStatus'
import { partitionProposals } from '@/lib/session/proposal-expiry'
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
    expiresAt: item.expires_at,
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
      const allPending = pendingRes.items.map(mapToProposal)
      // frontend 側でも期限切れをフィルタし、onProposalExpired hook を呼ぶ
      const { active } = partitionProposals(allPending)
      setProposals(active)
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

  const handleApprove = useCallback(async (id: string) => {
    setProposalStates((prev) => ({ ...prev, [id]: { status: 'approving' } }))
    try {
      const result = await apiPost<ProposalAPIResponse>(`/api/proposals/${id}/approve`, {})
      setProposalStates((prev) => ({
        ...prev,
        [id]: { status: 'success', txHash: result.tx_hash ?? undefined },
      }))
      setTimeout(() => {
        setProposals((prev) => prev.filter((p) => p.id !== id))
      }, 2000)
    } catch {
      setProposalStates((prev) => ({ ...prev, [id]: { status: 'pending' } }))
      setError('承認に失敗しました')
    }
  }, [])

  const handleReject = useCallback(async (id: string) => {
    try {
      await apiPost<ProposalAPIResponse>(`/api/proposals/${id}/reject`, {})
      setProposals((prev) => prev.filter((p) => p.id !== id))
      setProposalStates((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    } catch {
      setError('拒否に失敗しました')
    }
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
