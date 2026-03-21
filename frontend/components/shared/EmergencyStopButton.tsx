'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { AlertOctagon, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'

export interface EmergencyStopButtonProps {
  onStop: () => Promise<void>
  variant?: 'floating' | 'inline'
}

export function EmergencyStopButton({ onStop, variant = 'floating' }: EmergencyStopButtonProps) {
  const [isLoading, setIsLoading] = useState(false)

  const handleStop = async () => {
    setIsLoading(true)
    try {
      await onStop()
    } finally {
      setIsLoading(false)
    }
  }

  const trigger = (
    <Button
      variant="destructive"
      className={cn(
        'flex items-center gap-2 font-bold',
        variant === 'floating' && 'fixed bottom-6 right-6 z-50 shadow-lg rounded-full px-6 py-3 h-auto'
      )}
      disabled={isLoading}
    >
      {isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <AlertOctagon className="h-4 w-4" />
      )}
      緊急停止
    </Button>
  )

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        {trigger}
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="text-red-600 dark:text-red-400 flex items-center gap-2">
            <AlertOctagon className="h-5 w-5" />
            緊急停止の確認
          </AlertDialogTitle>
          <AlertDialogDescription className="text-sm leading-relaxed">
            本当に緊急停止しますか？全ての取引とAI判定が停止します。再開は手動でのみ可能です。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>キャンセル</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleStop}
            className="bg-red-600 hover:bg-red-700 text-white"
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                停止中...
              </>
            ) : (
              '緊急停止を実行'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
