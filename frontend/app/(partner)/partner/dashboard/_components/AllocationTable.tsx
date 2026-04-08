'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useCallback, useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import AllocationModal from './AllocationModal'
import {
  fetchAllocations,
  createAllocation,
  updateAllocation,
  deleteAllocation,
  type Allocation,
  type TesterPerformance,
  type CreateAllocationData,
  type UpdateAllocationData,
} from '@/lib/api/allocations'
import { getStoredToken } from '@/lib/auth'

interface Props {
  /** tester_name → TesterPerformance from /api/partner/performance */
  performanceMap?: Record<string, TesterPerformance>
}

function pnlColor(v: number): string {
  if (v > 0) return 'text-green-600 dark:text-green-400'
  if (v < 0) return 'text-red-600 dark:text-red-400'
  return 'text-gray-600 dark:text-gray-400'
}

function fmtUsd(v: number): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)
}

export default function AllocationTable({ performanceMap = {} }: Props) {
  const [allocations, setAllocations] = useState<Allocation[]>([])
  const [loading, setLoading] = useState(true)
  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null)
  const [selected, setSelected] = useState<Allocation | null>(null)

  const load = useCallback(async () => {
    const token = getStoredToken()
    if (!token) return
    setLoading(true)
    try {
      const items = await fetchAllocations(token)
      setAllocations(items)
    } catch {
      setAllocations([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function handleCreate(data: CreateAllocationData | UpdateAllocationData) {
    const token = getStoredToken()
    if (!token) return
    await createAllocation(token, data as CreateAllocationData)
    await load()
  }

  async function handleUpdate(data: CreateAllocationData | UpdateAllocationData) {
    const token = getStoredToken()
    if (!token || !selected) return
    await updateAllocation(token, selected.id, data as UpdateAllocationData)
    await load()
  }

  async function handleDelete() {
    const token = getStoredToken()
    if (!token || !selected) return
    await deleteAllocation(token, selected.id)
    await load()
  }

  function openCreate() {
    setSelected(null)
    setModalMode('create')
  }

  function openEdit(item: Allocation) {
    setSelected(item)
    setModalMode('edit')
  }

  function closeModal() {
    setModalMode(null)
    setSelected(null)
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">資金割り振り一覧</CardTitle>
          <Button size="sm" onClick={openCreate} className="gap-1">
            <Plus className="h-3.5 w-3.5" />
            追加
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded" />
              ))}
            </div>
          ) : allocations.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              割り振りデータがありません
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">名前</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">元本 (USD)</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">現在値 (USD)</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">損益 (USD)</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">利回り</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">割当日</th>
                  </tr>
                </thead>
                <tbody>
                  {allocations.map((item) => {
                    const perf = performanceMap[item.tester_name]
                    return (
                      <tr
                        key={item.id}
                        onClick={() => openEdit(item)}
                        className="border-b last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
                      >
                        <td className="px-4 py-3 font-medium">{item.tester_name}</td>
                        <td className="px-4 py-3 text-right">${fmtUsd(item.allocated_amount_usd)}</td>
                        <td className="px-4 py-3 text-right">
                          {perf?.current_value_usd != null ? `$${fmtUsd(perf.current_value_usd)}` : '—'}
                        </td>
                        <td className={`px-4 py-3 text-right font-medium ${perf?.pnl_usd != null ? pnlColor(perf.pnl_usd) : 'text-muted-foreground'}`}>
                          {perf?.pnl_usd != null
                            ? `${perf.pnl_usd >= 0 ? '+' : ''}$${fmtUsd(perf.pnl_usd)}`
                            : '—'}
                        </td>
                        <td className={`px-4 py-3 text-right font-medium ${perf?.pnl_percentage != null ? pnlColor(perf.pnl_percentage) : 'text-muted-foreground'}`}>
                          {perf?.pnl_percentage != null
                            ? `${perf.pnl_percentage >= 0 ? '+' : ''}${perf.pnl_percentage.toFixed(2)}%`
                            : '—'}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {new Date(item.allocated_at).toLocaleDateString('ja-JP')}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {modalMode !== null && (
        <AllocationModal
          mode={modalMode}
          allocation={selected}
          onClose={closeModal}
          onSubmit={modalMode === 'create' ? handleCreate : handleUpdate}
          onDelete={modalMode === 'edit' ? handleDelete : undefined}
        />
      )}
    </>
  )
}
