'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AssetIcon } from '@/components/shared/AssetIcon'
import { TransactionStatus, ProposalStatus } from './TransactionStatus'

export interface Proposal {
  id: string
  operation: 'SUPPLY' | 'WITHDRAW' | 'BORROW' | 'REPAY'
  asset: string
  amount: number
  amountUSD: number
  reason: string
  currentHF: number
  projectedHF: number
  estimatedGas: number
  slippage: number | null
  createdAt: string
  expiresAt: string
}

export interface ProposalCardProps {
  proposal: Proposal
  onApprove: (id: string) => Promise<void>
  onReject: (id: string) => void
  status: ProposalStatus
  txHash?: string
}

const operationBadgeConfig: Record<
  Proposal['operation'],
  { label: string; className: string }
> = {
  SUPPLY: {
    label: 'SUPPLY',
    className:
      'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
  },
  WITHDRAW: {
    label: 'WITHDRAW',
    className:
      'bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800',
  },
  BORROW: {
    label: 'BORROW',
    className:
      'bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800',
  },
  REPAY: {
    label: 'REPAY',
    className:
      'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800',
  },
}

function formatAmount(amount: number, asset: string): string {
  if (asset === 'USDC' || asset === 'USDT' || asset === 'DAI') {
    return amount.toLocaleString('ja-JP', { maximumFractionDigits: 2 })
  }
  return amount.toLocaleString('ja-JP', { maximumFractionDigits: 6 })
}

export function ProposalCard({
  proposal,
  onApprove,
  onReject,
  status,
  txHash,
}: ProposalCardProps) {
  const opConfig = operationBadgeConfig[proposal.operation]
  const hfDecreased = proposal.projectedHF < proposal.currentHF
  const hfColor = hfDecreased
    ? 'text-red-600 dark:text-red-400'
    : 'text-green-600 dark:text-green-400'
  const slippageWarning =
    proposal.slippage !== null && proposal.slippage > 0.5

  const isProcessing = status === 'approving' || status === 'confirming'
  const isDone = status === 'success' || status === 'failed'

  return (
    <Card className="w-full dark:bg-gray-900 border-border">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <AssetIcon symbol={proposal.asset} size="lg" />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge
                  variant="outline"
                  className={opConfig.className}
                >
                  {opConfig.label}
                </Badge>
                <span className="font-semibold text-base">
                  {proposal.asset}
                </span>
              </div>
              <p className="text-2xl font-bold mt-1 tracking-tight">
                {formatAmount(proposal.amount, proposal.asset)}{' '}
                <span className="text-sm font-normal text-muted-foreground">
                  {proposal.asset}
                </span>
              </p>
              <p className="text-sm text-muted-foreground">
                ≈ ${proposal.amountUSD.toLocaleString('ja-JP', { maximumFractionDigits: 2 })}
              </p>
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Reason */}
        <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">
          {proposal.reason}
        </p>

        {/* Metrics row */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="bg-muted/40 rounded-lg px-3 py-2">
            <p className="text-xs text-muted-foreground mb-0.5">ヘルスファクター変化</p>
            <p className={`font-semibold ${hfColor}`}>
              {proposal.currentHF.toFixed(2)} → {proposal.projectedHF.toFixed(2)}
            </p>
          </div>
          <div className="bg-muted/40 rounded-lg px-3 py-2">
            <p className="text-xs text-muted-foreground mb-0.5">推定ガス代</p>
            <p className="font-semibold">
              ~${proposal.estimatedGas.toFixed(2)}
            </p>
          </div>
        </div>

        {/* Slippage warning */}
        {slippageWarning && (
          <div className="flex items-center gap-2 text-sm text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg px-3 py-2">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            <span>
              スリッページが高めです（{proposal.slippage!.toFixed(2)}%）
            </span>
          </div>
        )}

        {/* Transaction status */}
        <TransactionStatus status={status} txHash={txHash} />

        {/* Action buttons */}
        {!isDone && (
          <div className="flex gap-2 pt-1">
            <Button
              className="flex-1 bg-green-600 hover:bg-green-700 text-white"
              onClick={() => onApprove(proposal.id)}
              disabled={isProcessing}
            >
              {isProcessing ? '処理中...' : '承認'}
            </Button>
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => onReject(proposal.id)}
              disabled={isProcessing}
            >
              却下
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
