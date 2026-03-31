'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useMemo } from 'react'
import { Users, Search } from 'lucide-react'
import { UserTable, UserDetailPanel } from './_components'
import type { UserDetail } from './_components/UserDetailPanel'

// ─── Mock data ────────────────────────────────────────────────────────────────
// TODO: Replace with GET /api/admin/users

const MOCK_USERS: UserDetail[] = [
  {
    id: 'user-001',
    address: '0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28',
    registeredAt: '2026-03-01T00:00:00Z',
    aum: 15000,
    lastActivity: '2026-03-21T14:30:00Z',
    riskMode: 'conservative' as const,
    status: 'NORMAL' as const,
    isPaused: false,
    positions: [
      { asset: 'USDC', supplied: 10000, borrowed: 0, usdValue: 10000 },
      { asset: 'WETH', supplied: 2.5, borrowed: 0, usdValue: 5000 },
    ],
    healthFactor: 2.1,
    hfHistory: Array.from({ length: 7 }, (_, i) => ({
      date: new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10),
      hf: 2.0 + Math.random() * 0.5,
    })),
    recentTrades: Array.from({ length: 5 }, (_, i) => ({
      id: `trade-${i}`,
      type: (['SUPPLY', 'WITHDRAW', 'BORROW'] as const)[i % 3],
      asset: 'USDC',
      amount: 1000 + i * 100,
      timestamp: new Date(Date.now() - i * 3600000).toISOString(),
    })),
    recentDecisions: Array.from({ length: 5 }, (_, i) => ({
      id: `dec-${i}`,
      action: (['BUY', 'SELL', 'HOLD'] as const)[i % 3],
      confidence: 60 + i * 5,
      timestamp: new Date(Date.now() - i * 7200000).toISOString(),
    })),
  },
  {
    id: 'user-002',
    address: '0xAbcD1234EfGh5678IjKl9012MnOp3456QrSt7890',
    registeredAt: '2026-03-10T00:00:00Z',
    aum: 8500,
    lastActivity: '2026-03-20T09:15:00Z',
    riskMode: 'balanced' as const,
    status: 'WARNING' as const,
    isPaused: false,
    positions: [{ asset: 'USDT', supplied: 8500, borrowed: 0, usdValue: 8500 }],
    healthFactor: 1.9,
    hfHistory: Array.from({ length: 7 }, (_, i) => ({
      date: new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10),
      hf: 1.8 + Math.random() * 0.3,
    })),
    recentTrades: [],
    recentDecisions: [],
  },
  {
    id: 'user-003',
    address: '0x1111222233334444555566667777888899990000',
    registeredAt: '2026-03-15T00:00:00Z',
    aum: 3200,
    lastActivity: '2026-03-19T22:00:00Z',
    riskMode: 'aggressive' as const,
    status: 'NORMAL' as const,
    isPaused: true,
    positions: [{ asset: 'WBTC', supplied: 0.1, borrowed: 0, usdValue: 3200 }],
    healthFactor: 3.5,
    hfHistory: Array.from({ length: 7 }, (_, i) => ({
      date: new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10),
      hf: 3.0 + Math.random() * 0.8,
    })),
    recentTrades: [],
    recentDecisions: [],
  },
]

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers] = useState<UserDetail[]>(MOCK_USERS)
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Filter by wallet address partial match
  const filteredUsers = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return users
    return users.filter((u) => u.address.toLowerCase().includes(q))
  }, [users, searchQuery])

  function handleTogglePause(userId: string, pause: boolean) {
    setUsers((prev) =>
      prev.map((u) => (u.id === userId ? { ...u, isPaused: pause } : u))
    )
    // Sync selectedUser state
    setSelectedUser((prev) =>
      prev && prev.id === userId ? { ...prev, isPaused: pause } : prev
    )
  }

  const totalAUM = users.reduce((sum, u) => sum + u.aum, 0)

  return (
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
              <span className="inline-flex items-center rounded-full bg-blue-900/50 border border-blue-800 px-2.5 py-0.5 text-xs font-semibold text-blue-300">
                {users.length}人
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              総AUM: ${totalAUM.toLocaleString('ja-JP')}
            </p>
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

      {/* Mock data banner */}
      <div className="mb-4 rounded-lg border border-amber-800 bg-amber-950/50 px-4 py-2 text-xs text-amber-300">
        準備中: ユーザー管理APIは現在実装中です。以下はサンプルデータです。
      </div>

      {/* ── User table ───────────────────────────────────────────────────── */}
      {filteredUsers.length === 0 ? (
        <EmptyState hasQuery={searchQuery.length > 0} />
      ) : (
        <UserTable users={filteredUsers} onSelectUser={setSelectedUser} />
      )}

      <p className="mt-2 text-xs text-gray-600">
        ※ 行をクリックするとユーザー詳細が表示されます。
      </p>

      {/* ── Detail panel ─────────────────────────────────────────────────── */}
      <UserDetailPanel
        user={selectedUser}
        onClose={() => setSelectedUser(null)}
        onTogglePause={handleTogglePause}
      />
    </>
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
