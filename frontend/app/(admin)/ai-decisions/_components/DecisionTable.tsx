'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { TradeActionBadge } from '@/components/shared/TradeActionBadge'
import type { AiDecision } from '../mock-data'

const PAGE_SIZE = 20

interface DecisionTableProps {
  decisions: AiDecision[]
  page: number
  onPageChange: (page: number) => void
  onRowClick: (decision: AiDecision) => void
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ja-JP', {
      timeZone: 'Asia/Tokyo',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function DecisionTable({
  decisions,
  page,
  onPageChange,
  onRowClick,
}: DecisionTableProps) {
  const totalPages = Math.max(1, Math.ceil(decisions.length / PAGE_SIZE))
  const paginated = decisions.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          判定履歴
          <span className="font-normal text-gray-400 dark:text-gray-500 text-xs ml-2">
            {decisions.length} 件
          </span>
        </h2>
      </div>

      {decisions.length === 0 ? (
        <div className="py-12 text-center text-sm text-gray-400">
          該当する判定履歴がありません。
        </div>
      ) : (
        <>
          <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-50 dark:bg-gray-800">
                  <TableHead className="text-gray-700 dark:text-gray-300 whitespace-nowrap">
                    日時
                  </TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">
                    クエリ
                  </TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">
                    判定
                  </TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300 text-right">
                    信頼度
                  </TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">
                    Claude判定
                  </TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">
                    GPT-4o判定
                  </TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300 text-center">
                    一致
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginated.map((d) => (
                  <TableRow
                    key={d.id}
                    onClick={() => onRowClick(d)}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950 transition-colors"
                  >
                    <TableCell className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {formatDateTime(d.timestamp)}
                    </TableCell>
                    <TableCell className="max-w-[200px]">
                      <span
                        className="block overflow-hidden text-ellipsis whitespace-nowrap text-sm text-gray-800 dark:text-gray-200"
                        title={d.query}
                      >
                        {d.query.length > 30
                          ? d.query.slice(0, 30) + '…'
                          : d.query}
                      </span>
                    </TableCell>
                    <TableCell>
                      <TradeActionBadge action={d.final_action} />
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap font-mono text-sm text-gray-800 dark:text-gray-200">
                      {Math.round(d.final_confidence * 100)}%
                    </TableCell>
                    <TableCell>
                      <TradeActionBadge action={d.claude_action} />
                    </TableCell>
                    <TableCell>
                      {d.gpt4o_action ? (
                        <TradeActionBadge action={d.gpt4o_action} />
                      ) : (
                        <span className="text-gray-400 text-xs">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-center">
                      <span
                        className={`text-base ${
                          d.agreed
                            ? 'text-green-600 dark:text-green-400'
                            : 'text-red-500 dark:text-red-400'
                        }`}
                      >
                        {d.agreed ? '✓' : '✗'}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-1">
              <button
                onClick={() => onPageChange(page - 1)}
                disabled={page === 1}
                className="px-3 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded-md disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                前へ
              </button>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => onPageChange(page + 1)}
                disabled={page === totalPages}
                className="px-3 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded-md disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                次へ
              </button>
            </div>
          )}

          <p className="text-xs text-gray-400 dark:text-gray-600">
            ※ 行をクリックすると詳細が表示されます。
          </p>
        </>
      )}
    </div>
  )
}
