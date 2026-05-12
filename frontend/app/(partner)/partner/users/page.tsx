'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useMemo, useEffect } from 'react'
import Link from 'next/link'
import { Users, Search, ExternalLink } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/api/client'
import type { UserResponse } from '@/lib/api/auth'
import { UserDetailModal } from './_components/UserDetailModal'
import { UserEditModal } from './_components/UserEditModal'

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  admin: '管理者',
  partner: 'パートナー',
  editor: '編集者',
  viewer: '閲覧者',
}

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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PartnerUsersPage() {
  const { token } = useAuth()
  const [users, setUsers] = useState<UserResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null)
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null)
  useEffect(() => {
    if (!token) return
    setLoading(true)
    apiFetch<UserResponse[]>('/users')
      .then(setUsers)
      .catch((e: unknown) => {
        const err = e as { message?: string }
        setFetchError(err.message ?? 'ユーザー一覧の取得に失敗しました')
      })
      .finally(() => setLoading(false))
  }, [token])

  const filteredUsers = useMemo(() => {
    let result = users
    const q = searchQuery.trim().toLowerCase()
    if (q) {
      result = result.filter(
        (u) =>
          u.username.toLowerCase().includes(q) ||
          u.email.toLowerCase().includes(q)
      )
    }
    if (statusFilter === 'active') {
      result = result.filter((u) => u.is_active)
    } else if (statusFilter === 'inactive') {
      result = result.filter((u) => !u.is_active)
    }
    return result
  }, [users, searchQuery, statusFilter])

  function handleUpdated(updated: UserResponse) {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
    setSelectedUser((prev) => (prev?.id === updated.id ? updated : prev))
    setEditingUser((prev) => (prev?.id === updated.id ? updated : prev))
  }

  function handleDeleted(userId: number) {
    setUsers((prev) => prev.filter((u) => u.id !== userId))
    setSelectedUser(null)
  }

  const activeCount = users.filter((u) => u.is_active).length
  const hasFilter = searchQuery.length > 0 || statusFilter !== 'all'

  return (
    <>
      <title>ユーザー管理 - Ultra AutoTrade</title>

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600/20">
            <Users className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-100">ユーザー管理</h1>
              <span className="inline-flex items-center rounded-full bg-blue-900/50 border border-blue-800 px-2.5 py-0.5 text-xs font-semibold text-blue-300">
                {users.length}人
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              アクティブ: {activeCount}人
            </p>
          </div>
        </div>

        <Link href="/partner/referral">
          <Button className="bg-blue-600 hover:bg-blue-700 text-white text-sm">
            紹介プログラムへ
          </Button>
        </Link>
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-500 pointer-events-none" />
          <input
            type="text"
            placeholder="名前・メールで検索..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 pl-9 pr-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
          />
        </div>

        <div className="flex gap-1.5">
          {(['all', 'active', 'inactive'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                statusFilter === s
                  ? 'bg-blue-600 text-white'
                  : 'border border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
              }`}
            >
              {s === 'all' ? '全て' : s === 'active' ? 'アクティブ' : '非アクティブ'}
            </button>
          ))}
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      {loading ? (
        <LoadingState />
      ) : fetchError ? (
        <ErrorState message={fetchError} />
      ) : filteredUsers.length === 0 ? (
        <EmptyState hasFilter={hasFilter} />
      ) : (
        <UsersTable users={filteredUsers} onSelect={setSelectedUser} />
      )}

      <p className="mt-2 text-xs text-gray-600">
        ※ 行をクリックするとユーザー詳細が表示されます。
      </p>

      {/* ── Modals ───────────────────────────────────────────────────────── */}
      <UserDetailModal
        user={selectedUser}
        token={token}
        onClose={() => setSelectedUser(null)}
        onUpdated={handleUpdated}
        onDeleted={handleDeleted}
        onEdit={(u) => setEditingUser(u)}
      />

      <UserEditModal
        user={editingUser}
        onClose={() => setEditingUser(null)}
        onUpdated={handleUpdated}
      />
    </>
  )
}

// ─── Users table ─────────────────────────────────────────────────────────────

function UsersTable({
  users,
  onSelect,
}: {
  users: UserResponse[]
  onSelect: (u: UserResponse) => void
}) {
  return (
    <div className="rounded-xl border border-gray-800 overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-gray-900 border-gray-800 hover:bg-gray-900">
            {['名前', 'メール', 'ロール', 'ステータス', '登録日', '最終更新', ''].map((h) => (
              <TableHead
                key={h}
                className="text-gray-400 font-medium text-xs uppercase tracking-wider"
              >
                {h}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => (
            <TableRow
              key={user.id}
              onClick={() => onSelect(user)}
              className="cursor-pointer border-gray-800 hover:bg-gray-800/60 transition-colors"
            >
              <TableCell className="py-3 text-gray-100 font-medium">
                {user.username}
              </TableCell>
              <TableCell className="py-3 text-gray-400 text-xs">{user.email}</TableCell>
              <TableCell className="py-3">
                <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-gray-700/50 text-gray-300">
                  {ROLE_LABELS[user.role] ?? user.role}
                </span>
              </TableCell>
              <TableCell className="py-3">
                <span
                  className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${
                    user.is_active
                      ? 'bg-green-900/50 text-green-300'
                      : 'bg-gray-700/50 text-gray-500'
                  }`}
                >
                  {user.is_active ? 'アクティブ' : '非アクティブ'}
                </span>
              </TableCell>
              <TableCell className="text-gray-400 text-xs py-3">
                {formatDate(user.created_at)}
              </TableCell>
              <TableCell className="text-gray-400 text-xs py-3">
                {formatDate(user.updated_at)}
              </TableCell>
              <TableCell className="py-3" onClick={(e) => e.stopPropagation()}>
                <Link
                  href={`/partner/users/${user.id}`}
                  className="inline-flex items-center gap-1 text-xs text-blue-400 hover:underline"
                >
                  詳細
                  <ExternalLink className="h-3 w-3" />
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

// ─── State components ─────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex items-center justify-center rounded-xl border border-gray-800 bg-gray-900/50 py-16">
      <p className="text-gray-500 text-sm">読み込み中...</p>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center rounded-xl border border-red-900 bg-red-950/30 py-16">
      <p className="text-red-400 text-sm">{message}</p>
    </div>
  )
}

function EmptyState({ hasFilter }: { hasFilter: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-gray-800 bg-gray-900/50 py-16 text-center">
      <Users className="h-10 w-10 text-gray-700 mb-3" />
      {hasFilter ? (
        <>
          <p className="text-gray-400 font-medium">該当するユーザーが見つかりません</p>
          <p className="text-gray-600 text-sm mt-1">検索条件を変更してください</p>
        </>
      ) : (
        <>
          <p className="text-gray-400 font-medium">登録ユーザーがいません</p>
          <p className="text-gray-600 text-sm mt-1">
            「紹介プログラムへ」から紹介リンクを発行できます
          </p>
        </>
      )}
    </div>
  )
}
