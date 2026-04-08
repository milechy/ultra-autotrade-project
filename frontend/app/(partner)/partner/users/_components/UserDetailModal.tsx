'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
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
import { apiPut } from '@/lib/api/client'
import { deleteUser } from '@/lib/api/users'
import type { UserResponse } from '@/lib/api/auth'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface UserDetailModalProps {
  user: UserResponse | null
  token: string | null
  onClose: () => void
  onUpdated: (user: UserResponse) => void
  onDeleted: (userId: number) => void
  onEdit?: (user: UserResponse) => void
}

// ─── Constants ────────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  admin: '管理者',
  partner: 'パートナー',
  editor: '編集者',
  viewer: '閲覧者',
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('ja-JP', {
      timeZone: 'Asia/Tokyo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return iso
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function UserDetailModal({
  user,
  token,
  onClose,
  onUpdated,
  onDeleted,
  onEdit,
}: UserDetailModalProps) {
  const [editing, setEditing] = useState(false)
  const [editUsername, setEditUsername] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState('')
  const [showConfirmDelete, setShowConfirmDelete] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  function handleStartEdit() {
    if (!user) return
    setEditUsername(user.username)
    setEditEmail(user.email)
    setEditError('')
    setEditing(true)
  }

  function handleCancelEdit() {
    setEditing(false)
    setEditError('')
  }

  async function handleSaveEdit() {
    if (!user) return
    setEditLoading(true)
    setEditError('')
    try {
      const updated = await apiPut<UserResponse>(`/users/${user.id}`, {
        username: editUsername || undefined,
        email: editEmail || undefined,
      })
      onUpdated(updated)
      setEditing(false)
    } catch (e: unknown) {
      const err = e as { message?: string }
      setEditError(err.message ?? '更新に失敗しました')
    } finally {
      setEditLoading(false)
    }
  }

  async function handleDelete() {
    if (!user || !token) return
    setDeleteLoading(true)
    setDeleteError('')
    try {
      await deleteUser(token, user.id)
      onDeleted(user.id)
      setShowConfirmDelete(false)
    } catch (e: unknown) {
      const err = e as { message?: string }
      setDeleteError(err.message ?? '削除に失敗しました')
    } finally {
      setDeleteLoading(false)
    }
  }

  function handleClose() {
    setEditing(false)
    setEditError('')
    setShowConfirmDelete(false)
    setDeleteError('')
    onClose()
  }

  return (
    <>
      <Dialog open={user !== null} onOpenChange={(o) => { if (!o) handleClose() }}>
        <DialogContent className="max-w-md bg-gray-950 border-gray-800">
          <DialogHeader>
            <DialogTitle className="text-gray-100">ユーザー詳細</DialogTitle>
            <DialogDescription className="text-gray-500 text-xs">
              {user ? `登録日: ${formatDate(user.created_at)}` : ''}
            </DialogDescription>
          </DialogHeader>

          {user && (
            <div className="space-y-4 text-sm">
              <div className="rounded-lg bg-gray-800/60 p-4 space-y-3">
                {editing ? (
                  <>
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">名前</label>
                      <input
                        value={editUsername}
                        onChange={(e) => setEditUsername(e.target.value)}
                        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">メール</label>
                      <input
                        type="email"
                        value={editEmail}
                        onChange={(e) => setEditEmail(e.target.value)}
                        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    {editError && (
                      <p className="text-xs text-red-400">{editError}</p>
                    )}
                    <div className="flex gap-2 justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCancelEdit}
                        className="border-gray-600 text-gray-300 hover:bg-gray-800"
                      >
                        キャンセル
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveEdit}
                        disabled={editLoading}
                        className="bg-blue-600 hover:bg-blue-700 text-white"
                      >
                        {editLoading ? '保存中...' : '保存'}
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="text-xs text-gray-500 mb-1">名前</div>
                      <div className="text-gray-100">{user.username}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">メール</div>
                      <div className="text-gray-100 text-xs break-all">{user.email}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">ロール</div>
                      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-gray-700/50 text-gray-300">
                        {ROLE_LABELS[user.role] ?? user.role}
                      </span>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">ステータス</div>
                      <span
                        className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${
                          user.is_active
                            ? 'bg-green-900/50 text-green-300'
                            : 'bg-gray-700/50 text-gray-500'
                        }`}
                      >
                        {user.is_active ? 'アクティブ' : '非アクティブ'}
                      </span>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">登録日</div>
                      <div className="text-gray-300 text-xs">{formatDate(user.created_at)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">最終更新</div>
                      <div className="text-gray-300 text-xs">{formatDate(user.updated_at)}</div>
                    </div>
                  </div>
                )}
              </div>

              {!editing && (
                <div className="flex items-center justify-between pt-2 border-t border-gray-800 gap-2 flex-wrap">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowConfirmDelete(true)}
                    className="border-red-800 text-red-400 hover:bg-red-950 hover:text-red-300"
                  >
                    削除
                  </Button>
                  <div className="flex gap-2">
                    {onEdit && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => { handleClose(); onEdit(user) }}
                        className="border-gray-600 text-gray-300 hover:bg-gray-800"
                      >
                        ログイン情報を編集
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={handleStartEdit}
                      className="bg-blue-600 hover:bg-blue-700 text-white"
                    >
                      編集
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete confirm dialog */}
      <Dialog
        open={showConfirmDelete}
        onOpenChange={(o) => {
          if (!o) {
            setShowConfirmDelete(false)
            setDeleteError('')
          }
        }}
      >
        <DialogContent className="max-w-sm bg-gray-900 border-gray-700">
          <DialogHeader>
            <DialogTitle className="text-gray-100">ユーザーを無効化しますか？</DialogTitle>
            <DialogDescription className="text-gray-400">
              このユーザーを削除します。この操作は取り消せません。
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p className="text-xs text-red-400">{deleteError}</p>}
          <div className="flex gap-2 justify-end pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowConfirmDelete(false)
                setDeleteError('')
              }}
              className="border-gray-600 text-gray-300 hover:bg-gray-800"
            >
              キャンセル
            </Button>
            <Button
              size="sm"
              onClick={handleDelete}
              disabled={deleteLoading}
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              {deleteLoading ? '削除中...' : '削除する'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
