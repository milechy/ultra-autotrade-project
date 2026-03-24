'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Clock } from 'lucide-react'
import { parseUnits } from 'ethers'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { apiFetch, apiPost } from '@/lib/api/client'
import { useAuth } from '@/lib/auth'
import { useWallet } from '@/hooks/useWallet'
import { useAaveV3 } from '@/hooks/useAaveV3'
import { getChainKey } from '@/lib/web3/config'
import type { SupportedToken } from '@/lib/web3/config'
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

// Token decimals map
const TOKEN_DECIMALS: Record<string, number> = {
  USDC: 6,
  USDT: 6,
  WBTC: 8,
  WETH: 18,
  DAI: 18,
}

const SUPPORTED_TOKENS = new Set<string>(['USDC', 'USDT', 'WBTC', 'WETH', 'DAI'])

function chainIdToName(chainId: number | undefined): string {
  if (chainId === 42161) return 'arbitrum'
  if (chainId === 421614) return 'arbitrum-sepolia'
  if (chainId === 84532) return 'base-sepolia'
  return 'arbitrum-sepolia'
}

function mapToProposal(item: ProposalAPIResponse): Proposal {
  return {
    id: String(item.id),
    operation: item.operation as Proposal['operation'],
    asset: item.asset,
    amount: parseFloat(item.amount),
    amountRaw: item.amount,
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
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const router = useRouter()
  const { isConnected, chainId } = useWallet()
  const { isReady, approve: approveToken, supply, withdraw, borrow, repay } = useAaveV3()

  const [proposals, setProposals] = useState<Proposal[]>([])
  const [recentApprovals, setRecentApprovals] = useState<RecentApproval[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [proposalStates, setProposalStates] = useState<Record<string, ProposalState>>({})

  const chain = chainIdToName(chainId)

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
    }
  }, [authLoading, isAuthenticated, router])

  useEffect(() => {
    if (isAuthenticated) { fetchData() }
  }, [fetchData, isAuthenticated])

  const handleApprove = useCallback(async (id: string) => {
    const proposal = proposals.find((p) => p.id === id)
    if (!proposal) return

    setProposalStates((prev) => ({ ...prev, [id]: { status: 'approving' } }))

    try {
      // ── Wallet signing path ──────────────────────────────────────────────
      if (isReady && isConnected && getChainKey(chainId ?? 0) && SUPPORTED_TOKENS.has(proposal.asset)) {
        const token = proposal.asset as SupportedToken
        const decimals = TOKEN_DECIMALS[proposal.asset] ?? 18
        const amount = parseUnits(proposal.amountRaw, decimals)

        // ERC20 approve required before SUPPLY / REPAY
        if (proposal.operation === 'SUPPLY' || proposal.operation === 'REPAY') {
          const approveTx = await approveToken(token, amount)
          await approveTx.wait(1)
        }

        let tx
        if (proposal.operation === 'SUPPLY') {
          tx = await supply(token, amount)
        } else if (proposal.operation === 'WITHDRAW') {
          tx = await withdraw(token, amount)
        } else if (proposal.operation === 'BORROW') {
          tx = await borrow(token, amount)
        } else {
          tx = await repay(token, amount)
        }

        setProposalStates((prev) => ({ ...prev, [id]: { status: 'confirming' } }))
        await tx.wait(1)
        const txHash = tx.hash

        // Notify backend of on-chain execution
        await apiPost<ProposalAPIResponse>(`/api/proposals/${id}/approve`, { tx_hash: txHash })

        setProposalStates((prev) => ({ ...prev, [id]: { status: 'success', txHash } }))
      } else {
        // ── REST fallback (managed mode / wallet not connected) ────────────
        const result = await apiPost<ProposalAPIResponse>(`/api/proposals/${id}/approve`, {})
        setProposalStates((prev) => ({
          ...prev,
          [id]: { status: 'success', txHash: result.tx_hash ?? undefined },
        }))
      }

      setTimeout(() => {
        setProposals((prev) => prev.filter((p) => p.id !== id))
      }, 2000)
    } catch {
      setProposalStates((prev) => ({ ...prev, [id]: { status: 'failed' } }))
      setError('承認に失敗しました')
    }
  }, [proposals, isReady, isConnected, chainId, approveToken, supply, withdraw, borrow, repay])

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

        {/* Wallet status indicator */}
        {isConnected && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
            <span>ウォレット接続済み — 承認時にMetaMaskで署名が必要です</span>
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="rounded-lg border border-red-800 bg-red-950 p-3">
            <p className="text-sm text-red-400">{error}</p>
            <button onClick={fetchData} className="text-xs text-blue-400 underline mt-1">再試行</button>
          </div>
        )}

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
                  chain={chain}
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
