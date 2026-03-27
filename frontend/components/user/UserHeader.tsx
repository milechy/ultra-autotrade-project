'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { ShieldAlert } from 'lucide-react'
import { useAccount } from 'wagmi'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { postJson } from '@/lib/api/http'
import { useAutomationStatus } from '@/components/user/UserProviders'

const navItems = [
  { href: '/user/dashboard', label: 'ダッシュボード' },
  { href: '/user/ai-feed', label: 'AI判定' },
  { href: '/user/approve', label: '取引承認' },
  { href: '/user/history', label: '取引履歴' },
  { href: '/user/settings', label: '設定' },
  { href: '/user/grid', label: 'Grid Bot' },
  { href: '/user/copy-trading', label: 'Copy Trading' },
  { href: '/user/wallet', label: 'ウォレット' },
]

export function UserHeader() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout, token } = useAuth()
  const { address, chain } = useAccount()
  const { isStopped, refreshStatus } = useAutomationStatus()
  const [showEmergencyConfirm, setShowEmergencyConfirm] = useState(false)

  const handleLogout = async () => {
    await logout()
    router.push('/connect')
  }

  const handleEmergencyStop = async () => {
    if (!token) return
    try {
      await postJson('/automation/emergency-stop', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await refreshStatus()
    } finally {
      setShowEmergencyConfirm(false)
    }
  }

  return (
    <>
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="flex items-center justify-between px-4 py-2">
          <Link href="/user/dashboard" className="font-bold text-sm shrink-0">
            Ultra AutoTrade
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1 overflow-x-auto">
            {navItems.map(({ href, label }) => {
              const isActive = pathname === href || pathname.startsWith(href + '/')
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    'px-3 py-1.5 rounded text-xs whitespace-nowrap transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  )}
                >
                  {label}
                </Link>
              )
            })}
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            {address && (
              <>
                <Badge variant="outline" className="font-mono text-xs hidden sm:flex">
                  {`${address.slice(0, 6)}...${address.slice(-4)}`}
                </Badge>
                <Badge
                  variant="outline"
                  className={cn(
                    'text-xs hidden sm:flex',
                    chain?.id === 42161
                      ? 'border-green-500/50 text-green-400'
                      : 'border-red-500/50 text-red-400'
                  )}
                >
                  {chain?.name ?? 'Unknown'}
                </Badge>
              </>
            )}
            {user && (
              <span className="hidden md:block text-xs text-muted-foreground">
                {user.username}
              </span>
            )}
            {isStopped ? (
              <span className="flex items-center justify-center h-7 w-7 rounded-full bg-destructive text-destructive-foreground">
                <ShieldAlert size={14} />
              </span>
            ) : (
              <button
                onClick={() => setShowEmergencyConfirm(true)}
                className="flex items-center justify-center h-7 w-7 rounded-full bg-destructive/90 hover:bg-destructive text-destructive-foreground transition-colors"
                aria-label="緊急停止"
              >
                <ShieldAlert size={14} />
              </button>
            )}
            <button
              onClick={handleLogout}
              className="text-xs border rounded px-2 py-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              ログアウト
            </button>
          </div>
        </div>

        {/* Mobile nav scroll */}
        <div className="md:hidden flex overflow-x-auto border-t scrollbar-none">
          {navItems.map(({ href, label }) => {
            const isActive = pathname === href || pathname.startsWith(href + '/')
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  'px-3 py-2 text-xs whitespace-nowrap shrink-0 border-b-2 transition-colors',
                  isActive
                    ? 'border-primary text-primary font-medium'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )}
              >
                {label}
              </Link>
            )
          })}
        </div>
      </header>

      {/* Emergency stop confirmation dialog */}
      {showEmergencyConfirm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-xl bg-background border p-6 shadow-xl">
            <p className="mb-4 text-base font-semibold">本当に全ての運用を停止しますか？</p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowEmergencyConfirm(false)}
                className="flex-1 rounded border px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                キャンセル
              </button>
              <button
                onClick={handleEmergencyStop}
                className="flex-1 rounded bg-destructive px-3 py-2 text-sm font-bold text-destructive-foreground hover:bg-destructive/90 transition-colors"
              >
                停止する
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}