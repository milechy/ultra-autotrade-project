// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { useAuth } from '@/lib/auth'
import { changePassword } from '@/lib/api/auth'

export function PasswordChangeCard() {
  const { token } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrent, setShowCurrent] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!currentPassword || !newPassword || !confirmPassword) {
      setError('すべての項目を入力してください')
      return
    }
    if (newPassword.length < 8) {
      setError('新しいパスワードは8文字以上必要です')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('新しいパスワードが一致しません')
      return
    }
    if (currentPassword === newPassword) {
      setError('新しいパスワードは現在のパスワードと異なる必要があります')
      return
    }
    if (!token) {
      setError('認証されていません')
      return
    }

    setIsSubmitting(true)
    try {
      await changePassword(token, {
        current_password: currentPassword,
        new_password: newPassword,
      })
      toast.success('パスワードを変更しました')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : null
      setError(message || '現在のパスワードが正しくありません')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-zinc-100">パスワード変更</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-4">
          {error && (
            <p className="rounded-lg border border-red-800 bg-red-950/40 px-3 py-2 text-sm text-red-400">
              {error}
            </p>
          )}

          {/* 現在のパスワード */}
          <div className="space-y-1.5">
            <Label htmlFor="current-password" className="text-zinc-300 text-sm">
              現在のパスワード
            </Label>
            <div className="relative">
              <Input
                id="current-password"
                type={showCurrent ? 'text' : 'password'}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                className="bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-500 pr-10"
              />
              <button
                type="button"
                onClick={() => setShowCurrent((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200"
                aria-label={showCurrent ? 'パスワードを隠す' : 'パスワードを表示'}
              >
                {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* 新しいパスワード */}
          <div className="space-y-1.5">
            <Label htmlFor="new-password" className="text-zinc-300 text-sm">
              新しいパスワード
            </Label>
            <div className="relative">
              <Input
                id="new-password"
                type={showNew ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                className="bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-500 pr-10"
              />
              <button
                type="button"
                onClick={() => setShowNew((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200"
                aria-label={showNew ? 'パスワードを隠す' : 'パスワードを表示'}
              >
                {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="text-xs text-zinc-500">8文字以上</p>
          </div>

          {/* 新しいパスワード（確認） */}
          <div className="space-y-1.5">
            <Label htmlFor="confirm-password" className="text-zinc-300 text-sm">
              新しいパスワード（確認）
            </Label>
            <div className="relative">
              <Input
                id="confirm-password"
                type={showConfirm ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                className="bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-500 pr-10"
              />
              <button
                type="button"
                onClick={() => setShowConfirm((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200"
                aria-label={showConfirm ? 'パスワードを隠す' : 'パスワードを表示'}
              >
                {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? '変更中...' : 'パスワードを変更'}
          </button>
        </form>
      </CardContent>
    </Card>
  )
}
