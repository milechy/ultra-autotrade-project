'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'

interface ManualTriggerModalProps {
  open: boolean
  onClose: () => void
}

export function ManualTriggerModal({ open, onClose }: ManualTriggerModalProps) {
  const [query, setQuery] = useState('')
  const [running, setRunning] = useState(false)
  const [resultMsg, setResultMsg] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setRunning(true)
    setResultMsg(null)
    try {
      // TODO: POST /api/ai/analyze
      await new Promise((resolve) => setTimeout(resolve, 1200))
      setResultMsg('AI判定を開始しました。しばらく後に履歴が更新されます。')
      setQuery('')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setResultMsg(`エラー: ${msg}`)
    } finally {
      setRunning(false)
    }
  }

  function handleClose() {
    setResultMsg(null)
    setQuery('')
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) handleClose() }}>
      <DialogContent className="max-w-md bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700">
        <DialogHeader>
          <DialogTitle className="text-gray-900 dark:text-gray-100">
            手動判定実行
          </DialogTitle>
          <DialogDescription className="text-gray-600 dark:text-gray-400">
            分析クエリを入力してAI判定を手動でトリガーします。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label
              htmlFor="manual-query"
              className="text-sm text-gray-700 dark:text-gray-300"
            >
              クエリ
            </Label>
            <Input
              id="manual-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例: BTC/USDT のトレンド分析..."
              className="bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600"
              disabled={running}
            />
          </div>

          {resultMsg && (
            <p
              className={`text-sm ${
                resultMsg.startsWith('エラー')
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-green-600 dark:text-green-400'
              }`}
            >
              {resultMsg}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={running}
              className="border-gray-300 dark:border-gray-600"
            >
              キャンセル
            </Button>
            <Button
              type="submit"
              disabled={running || !query.trim()}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              {running ? '実行中...' : '実行'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
