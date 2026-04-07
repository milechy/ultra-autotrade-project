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
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { triggerAIJudgment } from '@/lib/api/ai-decisions'
import type { AITriggerResponse } from '@/lib/api/ai-decisions'

interface ManualTriggerModalProps {
  open: boolean
  onClose: () => void
  /** 判定完了後に呼ばれるコールバック（一覧リフレッシュ用） */
  onTriggered?: () => void
}

export function ManualTriggerModal({ open, onClose, onTriggered }: ManualTriggerModalProps) {
  const { token } = useAuth()
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AITriggerResponse | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  async function handleTrigger() {
    if (!token) {
      setErrorMsg('認証されていません')
      return
    }
    setRunning(true)
    setResult(null)
    setErrorMsg(null)
    try {
      const res = await triggerAIJudgment(token)
      setResult(res)
      onTriggered?.()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message ?? String(err)
      setErrorMsg(msg || 'AI判定の実行に失敗しました')
    } finally {
      setRunning(false)
    }
  }

  function handleClose() {
    setResult(null)
    setErrorMsg(null)
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
            AI判定ジョブを今すぐ1回実行します。BUY/SELL判定時はアクティブユーザー全員に提案が作成されます。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Result */}
          {result && (
            <div className="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950 p-3 space-y-1 text-sm">
              <p className="font-semibold text-green-700 dark:text-green-300">判定完了</p>
              <p className="text-green-600 dark:text-green-400">
                判定: <span className="font-mono font-bold">{result.action}</span>
                {' '}（信頼度 {result.confidence}%）
              </p>
              <p className="text-green-600 dark:text-green-400">
                作成された提案: {result.proposals_created}件
              </p>
              <p className="text-xs text-green-500 dark:text-green-600">
                判定ID: {result.decision_id}
              </p>
            </div>
          )}

          {/* Error */}
          {errorMsg && (
            <p className="text-sm text-red-600 dark:text-red-400">
              エラー: {errorMsg}
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
              {result ? '閉じる' : 'キャンセル'}
            </Button>
            {!result && (
              <Button
                type="button"
                onClick={() => { void handleTrigger() }}
                disabled={running}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                {running ? '実行中...' : '実行'}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
