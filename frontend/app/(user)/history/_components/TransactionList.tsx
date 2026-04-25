// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState } from 'react'
import { FileX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { AssetIcon, TxHashLink } from '@/components/shared'
import { TransactionCard } from './TransactionCard'

export type TransactionType = 'SUPPLY' | 'WITHDRAW' | 'BORROW' | 'REPAY'
export type TransactionStatus = 'success' | 'pending' | 'failed'

export interface Transaction {
  id: string
  type: TransactionType
  asset: string
  amount: number
  amountUSD: number
  status: TransactionStatus
  txHash: string
  chain: 'arbitrum' | 'base' | 'base-sepolia' | 'ethereum'
  timestamp: string
}

const OPERATION_BADGE_CLASSES: Record<TransactionType, string> = {
  SUPPLY: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  WITHDRAW: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  BORROW: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  REPAY: 'bg-green-500/20 text-green-400 border-green-500/30',
}

const STATUS_BADGE_CLASSES: Record<TransactionStatus, string> = {
  success: 'bg-green-500/20 text-green-400 border-green-500/30',
  pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
}

const STATUS_LABELS: Record<TransactionStatus, string> = {
  success: '成功',
  pending: '処理中',
  failed: '失敗',
}

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const da = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${mo}-${da} ${h}:${mi}`
}

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  if (days > 0) return `${days}日前`
  if (hours > 0) return `${hours}時間前`
  if (minutes > 0) return `${minutes}分前`
  return 'たった今'
}

const PAGE_SIZE = 50

interface TransactionListProps {
  transactions: Transaction[]
}

export function TransactionList({ transactions }: TransactionListProps) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  const visible = transactions.slice(0, visibleCount)
  const hasMore = transactions.length > visibleCount

  if (transactions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-zinc-400">
        <FileX className="h-12 w-12 opacity-40" />
        <p className="text-sm font-medium">まだ取引履歴がありません</p>
        <p className="text-xs text-zinc-500">AI提案を承認すると、ここに取引履歴が表示されます</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Desktop table (md+) */}
      <div className="hidden md:block overflow-x-auto rounded-lg border border-zinc-800">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <TableHead className="text-zinc-400 font-medium">日時</TableHead>
              <TableHead className="text-zinc-400 font-medium">操作</TableHead>
              <TableHead className="text-zinc-400 font-medium">資産</TableHead>
              <TableHead className="text-zinc-400 font-medium text-right">金額</TableHead>
              <TableHead className="text-zinc-400 font-medium">ステータス</TableHead>
              <TableHead className="text-zinc-400 font-medium">Tx</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((tx) => (
              <TableRow key={tx.id} className="border-zinc-800 hover:bg-zinc-900/60">
                <TableCell className="whitespace-nowrap">
                  <div className="text-xs text-zinc-200">{formatDateTime(tx.timestamp)}</div>
                  <div className="text-xs text-zinc-500">{formatRelativeTime(tx.timestamp)}</div>
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={`text-xs px-2 py-0.5 ${OPERATION_BADGE_CLASSES[tx.type]}`}
                  >
                    {tx.type}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <AssetIcon symbol={tx.asset} size="sm" />
                    <span className="text-sm font-medium text-zinc-200">{tx.asset}</span>
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <span className="text-sm font-semibold text-zinc-100">
                    ${tx.amountUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={`text-xs px-2 py-0.5 ${STATUS_BADGE_CLASSES[tx.status]}`}
                  >
                    {STATUS_LABELS[tx.status]}
                  </Badge>
                </TableCell>
                <TableCell>
                  {tx.txHash ? (
                    <TxHashLink hash={tx.txHash} chain={tx.chain} truncate />
                  ) : (
                    <span className="text-zinc-600 text-xs">—</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile card list (< md) */}
      <div className="md:hidden space-y-2">
        {visible.map((tx) => (
          <TransactionCard key={tx.id} tx={tx} />
        ))}
      </div>

      {/* Load more */}
      {hasMore && (
        <div className="flex justify-center pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            もっと読み込む ({transactions.length - visibleCount}件)
          </Button>
        </div>
      )}
    </div>
  )
}
