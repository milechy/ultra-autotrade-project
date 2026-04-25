'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { CheckCircle2, XCircle, Loader2, ExternalLink } from 'lucide-react'

export type ProposalStatus = 'pending' | 'approving' | 'confirming' | 'success' | 'failed'

export interface TransactionStatusProps {
  status: ProposalStatus
  txHash?: string
  chain?: string
}

function getTxUrl(hash: string, chain?: string): string {
  if (chain === 'base-sepolia') return `https://sepolia.basescan.org/tx/${hash}`
  if (chain === 'base') return `https://basescan.org/tx/${hash}`
  if (chain === 'arbitrum') return `https://arbiscan.io/tx/${hash}`
  return `https://sepolia.basescan.org/tx/${hash}`
}

function TxLink({ hash, chain }: { hash: string; chain?: string }) {
  return (
    <a
      href={getTxUrl(hash, chain)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-mono text-sm underline-offset-4 hover:underline transition-colors"
    >
      {hash.slice(0, 6)}...{hash.slice(-4)}
      <ExternalLink className="h-3 w-3 flex-shrink-0" />
    </a>
  )
}

export function TransactionStatus({ status, txHash, chain }: TransactionStatusProps) {
  if (status === 'pending') return null

  if (status === 'approving') {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground mt-3 pt-3 border-t border-border">
        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
        <span>署名をリクエスト中...</span>
      </div>
    )
  }

  if (status === 'confirming') {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground mt-3 pt-3 border-t border-border">
        <Loader2 className="h-4 w-4 animate-spin text-yellow-500" />
        <span>確認待ち...</span>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div className="flex items-center gap-2 text-sm mt-3 pt-3 border-t border-border">
        <CheckCircle2 className="h-4 w-4 text-green-500 flex-shrink-0" />
        <span className="text-green-600 dark:text-green-400 font-medium">トランザクション完了</span>
        {txHash && (
          <span className="ml-auto">
            <TxLink hash={txHash} chain={chain} />
          </span>
        )}
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div className="flex items-center gap-2 text-sm mt-3 pt-3 border-t border-border">
        <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
        <div className="flex flex-col gap-0.5">
          <span className="text-red-600 dark:text-red-400 font-medium">トランザクション失敗</span>
          <span className="text-muted-foreground text-xs">再度「承認」ボタンを押してください</span>
        </div>
      </div>
    )
  }

  return null
}
