'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useMemo, useEffect } from 'react'
import { Users, Search } from 'lucide-react'
import AuthGuard from '@/components/AuthGuard'
import { UserTable, UserDetailPanel } from './_components'
import type { UserDetail } from './_components/UserDetailPanel'
import { fetchAdminUsers, pauseAdminUser, resumeAdminUser } from '@/lib/api/admin-users'
import type { AdminUserDetail } from '@/lib/api/admin-users'

// ─── Adapter ──────────────────────────────────────────────────────────────────

function toUserDetail(u: AdminUserDetail): UserDetail {
  return {
    id: u.id,
    address: u.address,
    registeredAt: u.registeredAt,
    aum: u.aum,
    lastActivity: u.lastActivity,
    riskMode: u.riskMode,
    status: u.status,
    isPaused: u.isPaused,
    positions: u.positions,
    healthFactor: u.healthFactor,
    hfHistory: u.hfHistory,
    recentTrades: u.recentTrades.map((t) => ({
      id: t.id,
      type: t.type as 'SUPPLY' | 'WITHDRAW' | 'BORROW',
      asset: t.asset,
      amount: t.amount,
      timestamp: t.timestamp,
    })),
    recentDecisions: u.recentDecisions.map((d) => ({
      id: d.id,
      action: d.action as 'BUY' | 'SELL' | 'HOLD',
      confidence: d.confidence,
      timestamp: d.timestamp,
    })),
  }
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers] = useState<UserDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    fetchAdminUsers()
      .then((data) => {
        setUsers(data.map(toUserDetail))
        setLoading(false)
      })
      .catch((err) => {
        setError(err?.message ?? 'データの取得に失敗しました')
        setLoading(false)
      })
  }, [])

  const filteredUsers = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return users
    return users.filter((u) => u.address.toLowerCase().includes(q))
  }, [users, searchQuery])

  async function handleTogglePause(userId: string, pause: boolean) {
    try {
      if (pause) {
        await pauseAdminUser(userId)
      } else {
        await resumeAdminUser(userId)
      }
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, isPaused: pause } : u))
      )
      setSelectedUser((prev) =>
        prev && prev.id === userId ? { ...prev, isPaused: pause } : prev
      )
    } catch {
      // エラー時は再取得してリセット
      fetchAdminUsers()
        .then((data) => setUsers(data.map(toUserDetail)))
        .catch(() => {})
    }
  }

  const totalAUM = users.reduce((sum, u) => sum + u.aum, 0)

  return (
    <AuthGuard adminOnly>
      <>
      <title>ユーザー管理 - Ultra AutoTrade</title>

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600/20">
            <Users className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-100">ユーザー管理</h1>
              {!loading && (
                <span className="inline-flex items-center rounded-full bg-blue-900/50 border border-blue-800 px-2.5 py-0.5 text-xs font-semibold text-blue-300">
                  {users.length}人
                </span>
              )}
            </div>
            {!loading && (
              <p className="text-xs text-gray-500 mt-0.5">
                総AUM: ${totalAUM.toLocaleString('ja-JP')}
              </p>
            )}
          </div>
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-500 pointer-events-none" />
          <input
            type="text"
            placeholder="ウォレットアドレスで検索..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 pl-9 pr-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
          />
        </div>
      </div>

      {/* ── States ───────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex items-center justify-center rounded-xl border border-gray-800 bg-gray-900/50 py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          <span className="ml-3 text-sm text-gray-400">読み込み中...</span>
        </div>
      )}

      {!loading && error && (
        <div className="rounded-lg border border-red-800 bg-red-950/50 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* ── User table ───────────────────────────────────────────────────── */}
      {!loading && !error && (
        <>
          {filteredUsers.length === 0 ? (
            <EmptyState hasQuery={searchQuery.length > 0} />
          ) : (
            <UserTable users={filteredUsers} onSelectUser={setSelectedUser} />
          )}
          <p className="mt-2 text-xs text-gray-600">
            ※ 行をクリックするとユーザー詳細が表示されます。
          </p>
        </>
      )}

      {/* ── Detail panel ─────────────────────────────────────────────────── */}
      <UserDetailPanel
        user={selectedUser}
        onClose={() => setSelectedUser(null)}
        onTogglePause={handleTogglePause}
      />
      </>
    </AuthGuard>
  )
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({ hasQuery }: { hasQuery: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-gray-800 bg-gray-900/50 py-16 text-center">
      <Users className="h-10 w-10 text-gray-700 mb-3" />
      {hasQuery ? (
        <>
          <p className="text-gray-400 font-medium">該当するユーザーが見つかりません</p>
          <p className="text-gray-600 text-sm mt-1">検索クエリを変更してください</p>
        </>
      ) : (
        <>
          <p className="text-gray-400 font-medium">登録ユーザーがいません</p>
          <p className="text-gray-600 text-sm mt-1">ユーザーが登録されると、ここに表示されます</p>
        </>
      )}
    </div>
  )
}
