'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { HelpCircle, ShieldAlert, ShieldOff } from 'lucide-react'
import { useAccount } from 'wagmi'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { postJson } from '@/lib/api/http'
import { useAutomationStatus } from '@/components/user/UserProviders'

const adminNavItems = [
  { href: '/user/dashboard', label: 'ダッシュボード' },
  { href: '/user/ai-feed', label: 'AI判定' },
  { href: '/user/approve', label: '取引承認' },
  { href: '/user/history', label: '取引履歴' },
  { href: '/user/deposit', label: '入金' },
  { href: '/user/settings', label: '設定' },
  { href: '/user/grid', label: 'Grid Bot' },
  { href: '/user/copy-trading', label: 'Copy Trading' },
  { href: '/user/wallet', label: 'ウォレット' },
]

// partner (非 admin) が /user/approve 等の user レイアウト画面に居るとき、
// user 用ナビではなく partner ポータルへの導線を出す。
const partnerNavItems = [
  { href: '/partner/dashboard', label: 'ダッシュボード' },
  { href: '/user/approve', label: '取引承認' },
  { href: '/partner/users', label: 'テスター管理' },
  { href: '/partner/referral', label: '紹介プログラム' },
  { href: '/partner/proposals', label: 'AI提案' },
  { href: '/partner/settings', label: '設定' },
]

const viewerNavItems = [
  { href: '/user/dashboard', label: 'ダッシュボード' },
  { href: '/user/ai-feed', label: 'AI判定' },
  { href: '/user/history', label: '取引履歴' },
]

export function UserHeader() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout, token, isAdmin, isPartner } = useAuth()
  const { address, chain } = useAccount()
  const { isStopped, refreshStatus } = useAutomationStatus()
  const [showEmergencyConfirm, setShowEmergencyConfirm] = useState(false)
  const [showResumeConfirm, setShowResumeConfirm] = useState(false)

  const handleLogout = async () => {
    await logout()
    router.push('/connect')
  }

  const handleEmergencyStop = async () => {
    if (!token) return
    try {
      await postJson('/api/automation/emergency-stop', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await refreshStatus()
    } finally {
      setShowEmergencyConfirm(false)
    }
  }

  const handleResume = async () => {
    if (!token) return
    try {
      await postJson('/api/automation/emergency-stop/resume', {}, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await refreshStatus()
    } finally {
      setShowResumeConfirm(false)
    }
  }

  return (
    <>
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="flex items-center justify-between px-4 py-2">
          <Link
            href={isAdmin || !isPartner ? '/user/dashboard' : '/partner/dashboard'}
            className="font-bold text-sm shrink-0"
          >
            Ultra AutoTrade
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1 overflow-x-auto">
            {(isAdmin
              ? adminNavItems
              : isPartner
                ? partnerNavItems
                : viewerNavItems
            ).map(({ href, label }) => {
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
            {(isAdmin || isPartner) && address && (
              <>
                <Badge variant="outline" className="font-mono text-xs hidden sm:flex">
                  {`${address.slice(0, 6)}...${address.slice(-4)}`}
                </Badge>
                <Badge
                  variant="outline"
                  className={cn(
                    'text-xs hidden sm:flex',
                    chain?.id === 84532
                      ? 'border-yellow-500/50 text-yellow-400'
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
            {isAdmin && (isStopped ? (
              <button
                onClick={() => setShowResumeConfirm(true)}
                className="flex items-center justify-center h-7 w-7 rounded-full bg-amber-500 hover:bg-amber-400 text-white transition-colors"
                aria-label="停止解除"
                title="停止解除"
              >
                <ShieldOff size={14} />
              </button>
            ) : (
              <button
                onClick={() => setShowEmergencyConfirm(true)}
                className="flex items-center justify-center h-7 w-7 rounded-full bg-destructive/90 hover:bg-destructive text-destructive-foreground transition-colors"
                aria-label="緊急停止"
              >
                <ShieldAlert size={14} />
              </button>
            ))}
            <Link
              href="/user/help"
              className="flex items-center justify-center h-7 w-7 rounded text-muted-foreground hover:text-foreground transition-colors"
              aria-label="ヘルプ"
              title="よくある質問"
            >
              <HelpCircle size={16} />
            </Link>
            <button
              onClick={handleLogout}
              className="text-xs border rounded px-2 py-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              ログアウト
            </button>
          </div>
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

      {/* Resume confirmation dialog */}
      {showResumeConfirm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-xl bg-background border p-6 shadow-xl">
            <p className="mb-2 text-base font-semibold">運用を再開しますか？</p>
            <p className="mb-4 text-sm text-amber-600 dark:text-amber-400">
              注意: Health Factor など自動条件が未改善の場合、再開後に再停止される可能性があります。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowResumeConfirm(false)}
                className="flex-1 rounded border px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                キャンセル
              </button>
              <button
                onClick={handleResume}
                className="flex-1 rounded bg-amber-500 px-3 py-2 text-sm font-bold text-white hover:bg-amber-400 transition-colors"
              >
                再開する
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}