// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { AssetIcon, TxHashLink } from '@/components/shared'
import type { Transaction } from './TransactionList'

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const da = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${mo}-${da} ${h}:${mi}`
}

type TFunc = (key: string, values?: Record<string, string | number>) => string

function formatRelativeTime(iso: string, t: TFunc): string {
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  if (days > 0) return t('daysAgo', { n: days })
  if (hours > 0) return t('hoursAgo', { n: hours })
  if (minutes > 0) return t('minutesAgo', { n: minutes })
  return t('justNow')
}

const OPERATION_BADGE_CLASSES: Record<Transaction['type'], string> = {
  SUPPLY: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  WITHDRAW: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  BORROW: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  REPAY: 'bg-green-500/20 text-green-400 border-green-500/30',
}

const STATUS_BADGE_CLASSES: Record<Transaction['status'], string> = {
  success: 'bg-green-500/20 text-green-400 border-green-500/30',
  pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
}

interface TransactionCardProps {
  tx: Transaction
}

export function TransactionCard({ tx }: TransactionCardProps) {
  const t = useTranslations('History')

  const operationLabel: Record<Transaction['type'], string> = {
    SUPPLY: t('opSupply'),
    WITHDRAW: t('opWithdraw'),
    BORROW: t('opBorrow'),
    REPAY: t('opRepay'),
  }

  const statusLabel: Record<Transaction['status'], string> = {
    success: t('statusSuccess'),
    pending: t('statusPending'),
    failed: t('statusFailed'),
  }

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          {/* Left: asset + operation */}
          <div className="flex items-center gap-3 min-w-0">
            <AssetIcon symbol={tx.asset} size="md" />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-sm text-zinc-100">{tx.asset}</span>
                <Badge
                  variant="outline"
                  className={`text-xs px-2 py-0.5 ${OPERATION_BADGE_CLASSES[tx.type]}`}
                >
                  {operationLabel[tx.type]}
                </Badge>
              </div>
              <div className="text-xs text-zinc-400 mt-0.5">
                <span>{formatDateTime(tx.timestamp)}</span>
                <span className="ml-2 text-zinc-500">({formatRelativeTime(tx.timestamp, t)})</span>
              </div>
            </div>
          </div>

          {/* Right: amount + status */}
          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            <span className="font-bold text-sm text-zinc-100">
              ${tx.amountUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <Badge
              variant="outline"
              className={`text-xs px-2 py-0.5 ${STATUS_BADGE_CLASSES[tx.status]}`}
            >
              {statusLabel[tx.status]}
            </Badge>
          </div>
        </div>

        {/* Tx hash */}
        {tx.txHash && (
          <div className="mt-3 pt-3 border-t border-zinc-800">
            <TxHashLink hash={tx.txHash} chain={tx.chain} truncate />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
