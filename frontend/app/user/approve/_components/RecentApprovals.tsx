'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import Link from 'next/link'
import { Badge } from '@/components/ui/badge'
import { AssetIcon } from '@/components/shared/AssetIcon'
import { TxHashLink } from '@/components/shared/TxHashLink'

export interface RecentApproval {
  id: string
  operation: string
  asset: string
  amount: number
  status: 'success' | 'failed'
  txHash: string
  timestamp: string
}

export interface RecentApprovalsProps {
  approvals: RecentApproval[]
}

function formatAmount(amount: number, asset: string): string {
  if (asset === 'USDC' || asset === 'USDT' || asset === 'DAI') {
    return amount.toLocaleString('ja-JP', { maximumFractionDigits: 2 })
  }
  return amount.toLocaleString('ja-JP', { maximumFractionDigits: 6 })
}

export function RecentApprovals({ approvals }: RecentApprovalsProps) {
  const displayItems = approvals.slice(0, 5)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">最近の承認履歴</h2>
        <Link
          href="/history"
          className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          全履歴を見る →
        </Link>
      </div>

      {displayItems.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4 text-center">
          承認履歴はありません
        </p>
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border overflow-hidden">
          {displayItems.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 px-4 py-3 bg-card hover:bg-muted/40 transition-colors"
            >
              <AssetIcon symbol={item.asset} size="sm" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground uppercase">
                    {item.operation}
                  </span>
                  <span className="text-sm font-medium truncate">
                    {formatAmount(item.amount, item.asset)} {item.asset}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <Badge
                  variant="outline"
                  className={
                    item.status === 'success'
                      ? 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800 text-xs'
                      : 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800 text-xs'
                  }
                >
                  {item.status === 'success' ? '成功' : '失敗'}
                </Badge>
                <TxHashLink hash={item.txHash} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
