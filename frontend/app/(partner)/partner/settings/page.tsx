'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { useAuth } from '@/lib/auth'
import { updateUser } from '@/lib/api/users'
import { PasswordChangeCard } from '@/app/(user)/settings/_components/PasswordChangeCard'

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

// ---- Page -------------------------------------------------------------------

export default function PartnerSettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold">設定</h1>
      <ProfileCard />
      <PasswordChangeCard />
    </div>
  )
}
