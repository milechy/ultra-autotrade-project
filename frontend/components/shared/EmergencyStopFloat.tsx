'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { OctagonX, Loader2, Play } from 'lucide-react'
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
import { postJson } from '@/lib/api/http'
import { useAuth } from '@/lib/auth'
import { useAutomationStatus } from '@/components/user/UserProviders'

export function EmergencyStopFloat() {
  const { token, isAdmin, isPartner } = useAuth()
  const { isStopped, refreshStatus } = useAutomationStatus()
  const [isLoading, setIsLoading] = useState(false)

  if (!isAdmin && !isPartner) return null

  const handleStop = async () => {
    if (!token) return
    setIsLoading(true)
    try {
      await postJson('/api/automation/emergency-stop', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await refreshStatus()
    } finally {
      setIsLoading(false)
    }
  }

  const handleResume = async () => {
    if (!token) return
    setIsLoading(true)
    try {
      await postJson('/api/automation/emergency-stop/resume', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await refreshStatus()
    } finally {
      setIsLoading(false)
    }
  }

  if (isStopped) {
    // admin は再開ボタン付きバナーを表示
    if (isAdmin) {
      return (
        <div className="fixed top-0 left-0 right-0 z-50 bg-red-600 text-white text-center text-sm font-semibold py-2 px-4 flex items-center justify-center gap-3">
          <OctagonX className="h-4 w-4 shrink-0" />
          <span>運用を停止中です</span>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="h-7 px-3 text-xs bg-white text-red-600 hover:bg-red-50 border-white"
                disabled={isLoading}
              >
                {isLoading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <>
                    <Play className="h-3 w-3 mr-1" />
                    再開
                  </>
                )}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2">
                  <Play className="h-5 w-5 text-green-600" />
                  運用を再開しますか？
                </AlertDialogTitle>
                <AlertDialogDescription>
                  自動取引を再開します。再開後は新しい取引が行われるようになります。
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={isLoading}>キャンセル</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleResume}
                  className="bg-green-600 hover:bg-green-700 text-white"
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      再開中...
                    </>
                  ) : (
                    '再開する'
                  )}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )
    }
    // partner は再開ボタンなしのバナーのみ
    return (
      <div className="fixed top-0 left-0 right-0 z-50 bg-red-600 text-white text-center text-sm font-semibold py-2 px-4 flex items-center justify-center gap-3">
        <OctagonX className="h-4 w-4 shrink-0" />
        <span>運用を停止中です（再開は管理者のみ）</span>
      </div>
    )
  }

  // 通常時 (停止していない): 緊急停止フロートボタンは admin のみに表示する。
  // partner の誤タップで本番運用が止まるリスクを避けるため。
  if (!isAdmin) return null

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <button
          className="fixed bottom-4 right-4 z-50 w-14 h-14 rounded-full bg-red-600 hover:bg-red-700 active:bg-red-800 text-white shadow-lg flex items-center justify-center transition-colors disabled:opacity-60"
          disabled={isLoading}
          aria-label="緊急停止"
          data-testid="emergency-stop-float"
        >
          {isLoading ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : (
            <OctagonX className="h-6 w-6" />
          )}
        </button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="text-red-600 dark:text-red-400 flex items-center gap-2">
            <OctagonX className="h-5 w-5" />
            本当に運用を停止しますか？
          </AlertDialogTitle>
          <AlertDialogDescription>
            停止中は新しい取引が行われません。再開はいつでも可能です。
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
              '停止する'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
