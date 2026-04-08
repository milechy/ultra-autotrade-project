'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Allocation, CreateAllocationData, UpdateAllocationData } from '@/lib/api/allocations'

interface AllocationModalProps {
  mode: 'create' | 'edit'
  allocation?: Allocation | null
  onClose: () => void
  onSubmit: (data: CreateAllocationData | UpdateAllocationData) => Promise<void>
  onDelete?: () => Promise<void>
}

export default function AllocationModal({
  mode,
  allocation,
  onClose,
  onSubmit,
  onDelete,
}: AllocationModalProps) {
  const [testerName, setTesterName] = useState('')
  const [amount, setAmount] = useState('')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (mode === 'edit' && allocation) {
      setTesterName(allocation.tester_name)
      setAmount(String(Number(allocation.allocated_amount_usd)))
      setNotes(allocation.notes ?? '')
    }
  }, [mode, allocation])

  function validate(): string | null {
    if (!testerName.trim()) return '名前は必須です'
    const amt = Number(amount)
    if (isNaN(amt) || amt <= 0) return '金額は0より大きい値を入力してください'
    return null
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    setError(null)
    setSubmitting(true)
    try {
      const data: CreateAllocationData | UpdateAllocationData = {
        tester_name: testerName.trim(),
        allocated_amount_usd: Number(amount),
        notes: notes.trim() || undefined,
      }
      await onSubmit(data)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '送信に失敗しました')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete() {
    if (!onDelete) return
    if (!confirm('この割り振りを削除しますか？')) return
    setDeleting(true)
    try {
      await onDelete()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '削除に失敗しました')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <CardTitle className="text-base">
            {mode === 'create' ? '資金割り振り追加' : '資金割り振り編集'}
          </CardTitle>
          <button
            onClick={onClose}
            className="rounded-sm opacity-70 hover:opacity-100 transition-opacity"
            aria-label="閉じる"
          >
            <X className="h-4 w-4" />
          </button>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="tester-name">
                テスター名 <span className="text-red-500">*</span>
              </label>
              <input
                id="tester-name"
                type="text"
                value={testerName}
                onChange={(e) => setTesterName(e.target.value)}
                placeholder="例: Alice"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="amount">
                割り当て金額 (USD) <span className="text-red-500">*</span>
              </label>
              <input
                id="amount"
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="例: 1000"
                min="0.01"
                step="0.01"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="notes">
                メモ
              </label>
              <textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="任意のメモ"
                rows={3}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            )}

            <div className="flex gap-2 pt-2">
              <Button type="submit" disabled={submitting} className="flex-1">
                {submitting ? '送信中...' : mode === 'create' ? '追加' : '更新'}
              </Button>
              {mode === 'edit' && onDelete && (
                <Button
                  type="button"
                  variant="destructive"
                  disabled={deleting}
                  onClick={handleDelete}
                >
                  {deleting ? '削除中...' : '削除'}
                </Button>
              )}
              <Button type="button" variant="outline" onClick={onClose}>
                キャンセル
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
