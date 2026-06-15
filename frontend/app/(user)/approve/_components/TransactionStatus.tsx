'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { TxHashLink } from '@/components/shared/TxHashLink'

export type ProposalStatus = 'pending' | 'approving' | 'confirming' | 'success' | 'failed'

export interface TransactionStatusProps {
  status: ProposalStatus
  txHash?: string
}

export function TransactionStatus({ status, txHash }: TransactionStatusProps) {
  const t = useTranslations('TransactionStatus')

  if (status === 'pending') return null

  if (status === 'approving') {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground mt-3 pt-3 border-t border-border">
        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
        <span>{t('requestingSignature')}</span>
      </div>
    )
  }

  if (status === 'confirming') {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground mt-3 pt-3 border-t border-border">
        <Loader2 className="h-4 w-4 animate-spin text-yellow-500" />
        <span>{t('waitingConfirmation')}</span>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div className="flex items-center gap-2 text-sm mt-3 pt-3 border-t border-border">
        <CheckCircle2 className="h-4 w-4 text-green-500 flex-shrink-0" />
        <span className="text-green-600 dark:text-green-400 font-medium">{t('txSuccess')}</span>
        {txHash && (
          <span className="ml-auto">
            <TxHashLink hash={txHash} />
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
          <span className="text-red-600 dark:text-red-400 font-medium">{t('txFailed')}</span>
          <span className="text-muted-foreground text-xs">{t('retryHint')}</span>
        </div>
      </div>
    )
  }

  return null
}
