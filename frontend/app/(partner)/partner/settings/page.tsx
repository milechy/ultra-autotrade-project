'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { toast } from 'sonner'
import { useAuth } from '@/lib/auth'
import { updateUser } from '@/lib/api/users'
import { PasswordChangeCard } from '@/app/(user)/settings/_components/PasswordChangeCard'
import { getStoredToken } from '@/lib/auth'
import { putJson, getJson } from '@/lib/api/http'

// ---- Profile Card (email + username) ----------------------------------------

function ProfileCard() {
  const { user, token } = useAuth()
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!token || !user) {
      setError('認証されていません')
      return
    }

    const updates: { email?: string; username?: string } = {}
    if (email.trim()) updates.email = email.trim()
    if (username.trim()) updates.username = username.trim()

    if (Object.keys(updates).length === 0) {
      setError('変更内容を入力してください')
      return
    }

    setIsSubmitting(true)
    try {
      await updateUser(token, user.id, updates)
      toast.success('プロフィールを更新しました')
      setEmail('')
      setUsername('')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : null
      setError(message || '更新に失敗しました')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">プロフィール変更</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Current values */}
        <div className="mb-4 space-y-1 rounded-lg bg-muted px-3 py-2 text-sm">
          <div className="flex gap-2">
            <span className="text-muted-foreground">現在のメール:</span>
            <span className="font-medium">{user?.email ?? '—'}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-muted-foreground">現在のユーザー名:</span>
            <span className="font-medium">{user?.username ?? '—'}</span>
          </div>
        </div>

        <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-4">
          {error && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400">
              {error}
            </p>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="new-email" className="text-sm">
              新しいメールアドレス
            </Label>
            <Input
              id="new-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="変更しない場合は空欄"
              autoComplete="email"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="new-username" className="text-sm">
              新しいユーザー名
            </Label>
            <Input
              id="new-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="変更しない場合は空欄"
              autoComplete="username"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? '更新中...' : 'プロフィールを更新'}
          </button>
        </form>
      </CardContent>
    </Card>
  )
}

// ---- Execution Mode Card ----------------------------------------------------

type UserMode = 'managed' | 'active'

interface UserSettingsData {
  user_mode: string
  execution_policy: string
}

function ExecutionModeCard() {
  const token = getStoredToken()
  const [currentMode, setCurrentMode] = useState<UserMode | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [pendingMode, setPendingMode] = useState<UserMode | null>(null)

  const loadSettings = useCallback(async () => {
    if (!token) return
    try {
      const data = await getJson<UserSettingsData>('/api/user/settings', {
        headers: { Authorization: `Bearer ${token}` },
      })
      setCurrentMode(data.user_mode === 'managed' ? 'managed' : 'active')
    } catch {
      toast.error('設定の取得に失敗しました')
    } finally {
      setIsLoading(false)
    }
  }, [token])

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  const handleConfirm = async () => {
    if (!token || !pendingMode) return
    setIsSaving(true)
    try {
      const data = await putJson<UserSettingsData>('/api/user/settings', {
        user_mode: pendingMode,
      }, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setCurrentMode(data.user_mode === 'managed' ? 'managed' : 'active')
      toast.success(pendingMode === 'managed' ? '自動実行モードに切り替えました' : '手動承認モードに切り替えました')
    } catch {
      toast.error('設定の更新に失敗しました')
    } finally {
      setIsSaving(false)
      setPendingMode(null)
    }
  }

  const modeLabel = (mode: UserMode) =>
    mode === 'managed' ? '自動実行' : '手動承認'

  const dialogDescription = pendingMode === 'managed'
    ? '自動実行に切り替えると、AIの判定が自動的に実行されます。安全装置（HF<1.6自動停止、取引上限10%、日次上限30%）は引き続き有効です。よろしいですか？'
    : '手動承認に切り替えますか？以降のAI提案は承認が必要になります。'

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">運用モード</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">読み込み中...</p>
        ) : (
          <>
            <div className="mb-2 text-sm text-muted-foreground">
              現在のモード:{' '}
              <span className="font-semibold text-foreground">
                {currentMode ? modeLabel(currentMode) : '—'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {(['active', 'managed'] as UserMode[]).map((mode) => (
                <AlertDialog key={mode} onOpenChange={(open) => { if (!open) setPendingMode(null) }}>
                  <AlertDialogTrigger asChild>
                    <button
                      onClick={() => setPendingMode(mode)}
                      disabled={currentMode === mode || isSaving}
                      className={[
                        'rounded-xl border-2 p-4 text-left transition-colors',
                        currentMode === mode
                          ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
                          : 'border-border hover:border-blue-400',
                        'disabled:cursor-not-allowed disabled:opacity-60',
                      ].join(' ')}
                    >
                      <div className="font-semibold text-sm">{modeLabel(mode)}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {mode === 'managed'
                          ? 'AIの判定を自動で実行（承認不要）'
                          : 'AIの提案をレビューしてから承認'}
                      </div>
                    </button>
                  </AlertDialogTrigger>
                  {pendingMode === mode && (
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>
                          {modeLabel(mode)}モードに切り替えますか？
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {dialogDescription}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>キャンセル</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => { void handleConfirm() }}
                          className="bg-blue-600 hover:bg-blue-700 text-white"
                        >
                          切り替える
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  )}
                </AlertDialog>
              ))}
            </div>

            <p className="text-xs text-muted-foreground pt-1">
              安全装置（HF&lt;1.6自動停止、取引上限10%、日次上限30%）はいずれのモードでも有効です。
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ---- Page -------------------------------------------------------------------

export default function PartnerSettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold">設定</h1>
      <ExecutionModeCard />
      <ProfileCard />
      <PasswordChangeCard />
    </div>
  )
}
