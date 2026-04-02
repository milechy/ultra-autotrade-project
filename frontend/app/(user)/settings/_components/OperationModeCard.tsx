// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { toast } from 'sonner'
import { apiPut } from '@/lib/api/client'
import { OperationModeSelector } from '@/components/OperationModeSelector'

type UserMode = 'managed' | 'active' | 'pro'

interface OperationModeCardProps {
  isRunning: boolean
  onToggle: (value: boolean) => void
  disabled?: boolean
  userMode?: string
  onModeChange?: (mode: string) => void
}

export function OperationModeCard({
  isRunning,
  onToggle,
  disabled = false,
  userMode = 'managed',
  onModeChange,
}: OperationModeCardProps) {
  const [pendingValue, setPendingValue] = useState<boolean | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const currentMode = (userMode as UserMode) in { managed: 1, active: 1, pro: 1 }
    ? (userMode as UserMode)
    : 'managed'

  const handleSwitchClick = (value: boolean) => {
    if (!value) {
      // 停止確認ダイアログを開く
      setPendingValue(false)
    } else {
      // 再開は確認なしで即時
      onToggle(true)
      toast('設定を保存しました')
    }
  }

  const handleConfirmStop = () => {
    onToggle(false)
    setPendingValue(null)
    toast('設定を保存しました')
  }

  const handleCancelStop = () => {
    setPendingValue(null)
  }

  const handleModeChange = async (mode: string) => {
    if (disabled || isSaving) return
    setIsSaving(true)
    try {
      await apiPut('/api/user/settings', { user_mode: mode })
      onModeChange?.(mode)
      toast('運用モードを変更しました')
    } catch {
      toast('モードの変更に失敗しました')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <>
      <Card className={`bg-zinc-900 border-zinc-800 ${disabled ? 'opacity-50 pointer-events-none' : ''}`}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-zinc-100">
            運用モード
            {disabled && <span className="ml-2 text-xs font-normal text-zinc-500">（管理者のみ変更可）</span>}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* ON/OFF スイッチ */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span
                className={`inline-block h-2.5 w-2.5 rounded-full flex-shrink-0 ${
                  isRunning ? 'bg-green-500' : 'bg-zinc-500'
                }`}
              />
              <div>
                <p className="text-sm font-medium text-zinc-100">
                  {isRunning ? '運用中' : '一時停止'}
                </p>
                <p className="text-xs text-zinc-400 mt-0.5">
                  {isRunning
                    ? 'AIによる分析と提案が有効です'
                    : 'AI分析と提案を停止中です。手動で再開してください'}
                </p>
              </div>
            </div>
            <Switch
              checked={isRunning}
              onCheckedChange={handleSwitchClick}
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">現在のステータス:</span>
            <StatusBadge status={isRunning ? 'NORMAL' : 'PAUSED'} />
          </div>

          {/* モード選択 */}
          <div className="pt-2 border-t border-zinc-800">
            <p className="text-xs text-zinc-400 mb-3">実行ポリシー</p>
            <OperationModeSelector
              currentMode={currentMode}
              onModeChange={handleModeChange}
              disabled={isSaving || disabled}
            />
          </div>
        </CardContent>
      </Card>

      <AlertDialog open={pendingValue === false} onOpenChange={(open) => { if (!open) handleCancelStop() }}>
        <AlertDialogContent className="bg-zinc-900 border-zinc-800">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-zinc-100">運用を一時停止しますか？</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              AI判定と取引提案が停止します。手動で再開するまで自動取引は行われません。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={handleCancelStop}
              className="bg-zinc-800 border-zinc-700 text-zinc-100 hover:bg-zinc-700"
            >
              キャンセル
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmStop}
              className="bg-orange-600 hover:bg-orange-700 text-white"
            >
              一時停止する
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
