'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { Badge } from '@/components/ui/badge'
import type { AdminProposal } from '@/lib/api/admin-proposals'

const PAGE_SIZE = 20

interface ProposalTableProps {
  proposals: AdminProposal[]
  page: number
  total: number
  onPageChange: (page: number) => void
  onRowClick: (proposal: AdminProposal) => void
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' })
  } catch {
    return iso
  }
}

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  pending: {
    label: '保留中',
    className: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  approved: {
    label: '承認済み',
    className: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400',
  },
  rejected: {
    label: '拒否',
    className: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400',
  },
  executed: {
    label: '実行済み',
    className: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400',
  },
  expired: {
    label: '期限切れ',
    className: 'bg-gray-100 text-gray-500 border-gray-200 dark:bg-gray-800 dark:text-gray-400',
  },
}

const OP_CONFIG: Record<string, { label: string; className: string }> = {
  SUPPLY: { label: 'SUPPLY', className: 'bg-green-100 text-green-800 border-green-200' },
  WITHDRAW: { label: 'WITHDRAW', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
  BORROW: { label: 'BORROW', className: 'bg-orange-100 text-orange-800 border-orange-200' },
  REPAY: { label: 'REPAY', className: 'bg-blue-100 text-blue-800 border-blue-200' },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: '' }
  return (
    <Badge variant="outline" className={`text-xs px-2 py-0.5 ${cfg.className}`}>
      {cfg.label}
    </Badge>
  )
}

function OperationBadge({ operation }: { operation: string }) {
  const cfg = OP_CONFIG[operation] ?? { label: operation, className: '' }
  return (
    <Badge variant="outline" className={`text-xs px-2 py-0.5 ${cfg.className}`}>
      {cfg.label}
    </Badge>
  )
}

export function ProposalTable({
  proposals,
  page,
  total,
  onPageChange,
  onRowClick,
}: ProposalTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-3">
      {/* Desktop table */}
      <div className="hidden md:block rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">ID</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">ユーザー</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">操作</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">資産</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">金額 (USD)</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 max-w-xs">理由</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">ステータス</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">作成日時</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">期限</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {proposals.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-sm text-gray-400">
                  条件に一致する提案がありません
                </td>
              </tr>
            ) : (
              proposals.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => onRowClick(p)}
                  className="hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 text-xs text-gray-500 font-mono">#{p.id}</td>
                  <td className="px-4 py-3">
                    <div className="text-xs font-medium text-gray-800 dark:text-gray-200">
                      {p.username ?? `user_${p.user_id}`}
                    </div>
                    {p.email && (
                      <div className="text-xs text-gray-400 truncate max-w-[140px]">{p.email}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <OperationBadge operation={p.operation} />
                  </td>
                  <td className="px-4 py-3 text-xs font-medium text-gray-700 dark:text-gray-300">
                    {p.asset}
                  </td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-800 dark:text-gray-200">
                    ${Number(p.amount_usd).toLocaleString('ja-JP', { maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 max-w-xs">
                    <span className="line-clamp-2">{p.reason}</span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDateTime(p.created_at)}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDateTime(p.expires_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {proposals.length === 0 ? (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-400">
            条件に一致する提案がありません
          </div>
        ) : (
          proposals.map((p) => (
            <div
              key={p.id}
              onClick={() => onRowClick(p)}
              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm space-y-2 cursor-pointer active:bg-gray-50"
            >
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  <OperationBadge operation={p.operation} />
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
                    {p.asset}
                  </span>
                </div>
                <StatusBadge status={p.status} />
              </div>
              <div className="text-xs text-gray-500">
                {p.username ?? `user_${p.user_id}`}
                {p.email && ` · ${p.email}`}
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400 text-xs">金額</span>
                <span className="font-mono text-gray-800 dark:text-gray-200 text-xs">
                  ${Number(p.amount_usd).toLocaleString('ja-JP', { maximumFractionDigits: 2 })}
                </span>
              </div>
              <p className="text-xs text-gray-500 line-clamp-2">{p.reason}</p>
              <div className="text-xs text-gray-400">{formatDateTime(p.created_at)}</div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-3 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            前へ
          </button>
          <span className="text-xs text-gray-600 dark:text-gray-400">
            {page} / {totalPages}（全 {total} 件）
          </span>
          <button
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            次へ
          </button>
        </div>
      )}
    </div>
  )
}
