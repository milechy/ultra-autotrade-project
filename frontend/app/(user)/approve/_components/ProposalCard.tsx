'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useState } from 'react'
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
  /** AI 判定根拠 (rag_context_json)。API から渡る場合のみ表示。 */
  ragContext?: Record<string, unknown> | null
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

  // 旧実装で使っていた isProcessing は P5 display-only 化により不要
  const isDone = status === 'success' || status === 'failed'

  // AI 判定根拠 (rag_context_json) を expandable で表示
  const [showRag, setShowRag] = useState(false)
  const hasRag =
    proposal.ragContext !== null &&
    proposal.ragContext !== undefined &&
    Object.keys(proposal.ragContext).length > 0

  // P5 display-only: 承認/却下 ボタンは完全に非活性。
  // onApprove / onReject は親 (page.tsx) から渡されるが、本コンポーネントの
  // ボタンが常に disabled なので発火することはない。
  // 後で manual UI を「click だけログを取る」モードに戻す可能性があるため
  // props のシグネチャは残す。lint の no-unused-vars を回避するため void で消費。
  void onApprove
  void onReject

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

        {/* AI 判定根拠 (rag_context_json) — 読み取り専用 expandable */}
        {hasRag && (
          <div className="rounded-lg border border-zinc-700 bg-zinc-900/40">
            <button
              type="button"
              onClick={() => setShowRag((v) => !v)}
              aria-expanded={showRag}
              data-testid="proposal-rag-toggle"
              className="w-full flex items-center justify-between px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-800/40 rounded-lg"
            >
              <span>
                {showRag ? '▼' : '▶'} AI 判定根拠 (rag_context)
              </span>
              <span className="text-[10px] text-zinc-500">読み取り専用</span>
            </button>
            {showRag && (
              <pre
                data-testid="proposal-rag-content"
                className="text-[11px] text-zinc-400 px-3 pb-3 overflow-x-auto whitespace-pre-wrap break-words leading-relaxed"
              >
                {(() => {
                  try {
                    return JSON.stringify(proposal.ragContext, null, 2)
                  } catch {
                    return '[rag_context_json parse error]'
                  }
                })()}
              </pre>
            )}
          </div>
        )}

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

        {/* Action buttons (P5 display-only: ボタンは完全に非活性。実取引は AI が自動執行) */}
        {!isDone && (
          <div className="flex flex-col gap-1.5 pt-1">
            <div className="flex gap-2">
              <Button
                className="flex-1 bg-green-600 text-white opacity-50 cursor-not-allowed"
                disabled
                aria-disabled="true"
                title="実行は自動です"
                data-testid="proposal-approve-button"
                tabIndex={-1}
              >
                承認（自動執行）
              </Button>
              <Button
                variant="outline"
                className="flex-1 opacity-50 cursor-not-allowed"
                disabled
                aria-disabled="true"
                title="実行は自動です"
                data-testid="proposal-reject-button"
                tabIndex={-1}
              >
                却下（自動執行）
              </Button>
            </div>
            {/* P5 display-only label: 法務 sign-off 後に文言は最終化 */}
            <small className="text-xs text-amber-500">
              ⚠️ 本機能は機能説明用です。実取引は AI が全自動で実行します。
            </small>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
