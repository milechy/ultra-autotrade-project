'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { apiPut } from '@/lib/api/client'
import type { UserResponse } from '@/lib/api/auth'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface UserEditModalProps {
  user: UserResponse | null
  onClose: () => void
  onUpdated: (user: UserResponse) => void
}

interface UpdatePayload {
  email?: string
  username?: string
  password?: string
  is_active?: boolean
}

// ─── Input helper ─────────────────────────────────────────────────────────────

function Field({
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  hint?: string
}) {
  return (
    <div>
      <label className="text-xs text-gray-400 mb-1 block">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={type === 'password' ? 'new-password' : undefined}
        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
      />
      {hint && <p className="text-xs text-gray-600 mt-1">{hint}</p>}
    </div>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

export function UserEditModal({ user, onClose, onUpdated }: UserEditModalProps) {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  // Reset form whenever a different user is opened
  useEffect(() => {
    if (user) {
      setEmail(user.email)
      setUsername(user.username)
      setPassword('')
      setIsActive(user.is_active)
      setError('')
      setSuccess(false)
    }
  }, [user])

  function handleClose() {
    setError('')
    setSuccess(false)
    onClose()
  }

  async function handleSave() {
    if (!user) return
    setLoading(true)
    setError('')
    setSuccess(false)

    const payload: UpdatePayload = {}
    if (email && email !== user.email) payload.email = email
    if (username && username !== user.username) payload.username = username
    if (password) payload.password = password
    if (isActive !== user.is_active) payload.is_active = isActive

    if (Object.keys(payload).length === 0) {
      setError('変更がありません')
      setLoading(false)
      return
    }

    try {
      const updated = await apiPut<UserResponse>(`/users/${user.id}`, payload)
      onUpdated(updated)
      setSuccess(true)
      setPassword('')
      // Auto-close after brief success flash
      setTimeout(handleClose, 800)
    } catch (e: unknown) {
      const err = e as { message?: string }
      setError(err.message ?? '更新に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={user !== null} onOpenChange={(o) => { if (!o) handleClose() }}>
      <DialogContent className="max-w-md bg-gray-950 border-gray-800">
        <DialogHeader>
          <DialogTitle className="text-gray-100">ログイン情報を編集</DialogTitle>
          <DialogDescription className="text-gray-500 text-xs">
            {user?.username} のアカウント情報を変更します
          </DialogDescription>
        </DialogHeader>

        {user && (
          <div className="space-y-4 pt-1">
            {/* Fields */}
            <div className="rounded-lg bg-gray-800/50 p-4 space-y-3">
              <Field
                label="メールアドレス"
                type="email"
                value={email}
                onChange={setEmail}
              />
              <Field
                label="ユーザー名"
                value={username}
                onChange={setUsername}
              />
              <Field
                label="新しいパスワード"
                type="password"
                value={password}
                onChange={setPassword}
                placeholder="空欄 = 変更しない"
                hint="8文字以上。空欄のままにすると変更されません。"
              />

              {/* is_active toggle */}
              <div>
                <label className="text-xs text-gray-400 mb-2 block">ステータス</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setIsActive(true)}
                    className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? 'border-green-600 bg-green-900/40 text-green-300'
                        : 'border-gray-700 bg-gray-800 text-gray-500 hover:border-gray-600'
                    }`}
                  >
                    アクティブ
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsActive(false)}
                    className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors ${
                      !isActive
                        ? 'border-red-700 bg-red-900/40 text-red-400'
                        : 'border-gray-700 bg-gray-800 text-gray-500 hover:border-gray-600'
                    }`}
                  >
                    非アクティブ
                  </button>
                </div>
              </div>
            </div>

            {/* Error / success */}
            {error && (
              <p className="text-xs text-red-400 px-1">{error}</p>
            )}
            {success && (
              <p className="text-xs text-green-400 px-1">保存しました</p>
            )}

            {/* Actions */}
            <div className="flex gap-2 justify-end pt-1">
              <Button
                variant="outline"
                size="sm"
                onClick={handleClose}
                disabled={loading}
                className="border-gray-600 text-gray-300 hover:bg-gray-800"
              >
                キャンセル
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={loading}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                {loading ? '保存中...' : '保存'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
