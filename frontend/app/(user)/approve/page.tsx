'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useState, useCallback } from 'react'
import { Clock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  ProposalCard,
  RecentApprovals,
  ProposalStatus,
  Proposal,
  RecentApproval,
} from './_components'

// TODO: Replace with GET /api/proposals/pending
const MOCK_PROPOSALS: Proposal[] = [
  {
    id: 'prop-001',
    operation: 'SUPPLY',
    asset: 'USDC',
    amount: 1500,
    amountUSD: 1500,
    reason:
      '現在のUSDC supply APRが4.2%と高水準です。遊休資金の一部をAaveに供給し、利回りを獲得することを提案します。',
    currentHF: 2.1,
    projectedHF: 1.9,
    estimatedGas: 0.15,
    slippage: null,
    createdAt: '2026-03-21T09:00:00Z',
  },
  {
    id: 'prop-002',
    operation: 'SUPPLY',
    asset: 'WETH',
    amount: 0.5,
    amountUSD: 1650,
    reason:
      'ETH supply APR 1.95%。ETH保有中のため流動性を維持しつつ利回り獲得を推奨。',
    currentHF: 2.1,
    projectedHF: 2.3,
    estimatedGas: 0.18,
    slippage: null,
    createdAt: '2026-03-21T09:05:00Z',
  },
]

// TODO: Replace with GET /api/proposals/history
const MOCK_RECENT: RecentApproval[] = [
  {
    id: 'past-1',
    operation: 'SUPPLY',
    asset: 'USDC',
    amount: 2000,
    status: 'success',
    txHash: '0xabc123',
    timestamp: '2026-03-20T14:00:00Z',
  },
  {
    id: 'past-2',
    operation: 'WITHDRAW',
    asset: 'WETH',
    amount: 0.3,
    status: 'success',
    txHash: '0xdef456',
    timestamp: '2026-03-19T10:00:00Z',
  },
]

type ProposalState = {
  status: ProposalStatus
  txHash?: string
}

export default function ApprovePage() {
  const [proposals, setProposals] = useState<Proposal[]>(MOCK_PROPOSALS)
  const [proposalStates, setProposalStates] = useState<
    Record<string, ProposalState>
  >({})

  const handleApprove = useCallback(async (id: string) => {
    // Mock: approving → confirming → success (2s total)
    setProposalStates((prev) => ({
      ...prev,
      [id]: { status: 'approving' },
    }))

    await new Promise((resolve) => setTimeout(resolve, 1000))

    setProposalStates((prev) => ({
      ...prev,
      [id]: { status: 'confirming' },
    }))

    await new Promise((resolve) => setTimeout(resolve, 1000))

    setProposalStates((prev) => ({
      ...prev,
      [id]: {
        status: 'success',
        txHash: `0x${Math.random().toString(16).slice(2, 18)}`,
      },
    }))
  }, [])

  const handleReject = useCallback((id: string) => {
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

        {/* Proposal list */}
        {proposals.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
            <Clock className="h-10 w-10 opacity-40" />
            <p className="text-sm font-medium">承認待ちの提案はありません</p>
            <p className="text-xs">AIが新しい提案を作成するとここに表示されます</p>
          </div>
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
        <RecentApprovals approvals={MOCK_RECENT} />
      </div>
    </div>
  )
}
