'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { HelpCircle, ShieldAlert, ShieldOff } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useWallet } from '@/hooks/useWallet'
import { getChainDisplayName } from '@/lib/web3/config'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { postJson } from '@/lib/api/http'
import { useAutomationStatus } from '@/components/user/UserProviders'

export function UserHeader() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, logout, token, isAdmin, isPartner } = useAuth()
  const t = useTranslations('UserHeader')
  // injected / Privy embedded を統合した単一情報源（useWallet）から取得。
  const { address, chainId } = useWallet()
  const { isStopped, refreshStatus } = useAutomationStatus()
  const [showEmergencyConfirm, setShowEmergencyConfirm] = useState(false)
  const [showResumeConfirm, setShowResumeConfirm] = useState(false)

  const adminNavItems = [
    { href: '/user/dashboard', label: t('adminNav.dashboard') },
    { href: '/user/ai-feed', label: t('adminNav.aiFeed') },
    { href: '/user/approve', label: t('adminNav.approve') },
    { href: '/user/history', label: t('adminNav.history') },
    { href: '/user/deposit', label: t('adminNav.deposit') },
    { href: '/user/settings', label: t('adminNav.settings') },
    { href: '/user/grid', label: t('adminNav.gridBot') },
    { href: '/user/copy-trading', label: t('adminNav.copyTrading') },
    { href: '/user/wallet', label: t('adminNav.wallet') },
  ]

  // partner (非 admin) が /user/approve 等の user レイアウト画面に居るとき、
  // user 用ナビではなく partner ポータルへの導線を出す。
  const partnerNavItems = [
    { href: '/partner/dashboard', label: t('partnerNav.dashboard') },
    { href: '/user/approve', label: t('partnerNav.approve') },
    { href: '/partner/users', label: t('partnerNav.users') },
    { href: '/partner/referral', label: t('partnerNav.referral') },
    { href: '/partner/proposals', label: t('partnerNav.proposals') },
    { href: '/partner/settings', label: t('partnerNav.settings') },
  ]

  const viewerNavItems = [
    { href: '/user/dashboard', label: t('viewerNav.dashboard') },
    { href: '/user/ai-feed', label: t('viewerNav.aiFeed') },
    { href: '/user/history', label: t('viewerNav.history') },
  ]

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
                    chainId === 84532
                      ? 'border-yellow-500/50 text-yellow-400'
                      : 'border-red-500/50 text-red-400'
                  )}
                >
                  {getChainDisplayName(chainId) ?? 'Unknown'}
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
                aria-label={t('resumeAriaLabel')}
                title={t('resumeAriaLabel')}
              >
                <ShieldOff size={14} />
              </button>
            ) : (
              <button
                onClick={() => setShowEmergencyConfirm(true)}
                className="flex items-center justify-center h-7 w-7 rounded-full bg-destructive/90 hover:bg-destructive text-destructive-foreground transition-colors"
                aria-label={t('emergencyStopAriaLabel')}
              >
                <ShieldAlert size={14} />
              </button>
            ))}
            <Link
              href="/user/help"
              className="flex items-center justify-center h-7 w-7 rounded text-muted-foreground hover:text-foreground transition-colors"
              aria-label={t('helpAriaLabel')}
              title={t('helpTitle')}
            >
              <HelpCircle size={16} />
            </Link>
            {(user || token) && (
              <button
                onClick={handleLogout}
                className="text-xs border rounded px-2 py-1 text-muted-foreground hover:text-foreground transition-colors"
              >
                {t('logout')}
              </button>
            )}
          </div>
        </div>

      </header>

      {/* Emergency stop confirmation dialog */}
      {showEmergencyConfirm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-xl bg-background border p-6 shadow-xl">
            <p className="mb-4 text-base font-semibold">{t('confirmStopTitle')}</p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowEmergencyConfirm(false)}
                className="flex-1 rounded border px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                {t('cancelButton')}
              </button>
              <button
                onClick={handleEmergencyStop}
                className="flex-1 rounded bg-destructive px-3 py-2 text-sm font-bold text-destructive-foreground hover:bg-destructive/90 transition-colors"
              >
                {t('stopButton')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Resume confirmation dialog */}
      {showResumeConfirm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-sm rounded-xl bg-background border p-6 shadow-xl">
            <p className="mb-2 text-base font-semibold">{t('confirmResumeTitle')}</p>
            <p className="mb-4 text-sm text-amber-600 dark:text-amber-400">
              {t('resumeWarning')}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowResumeConfirm(false)}
                className="flex-1 rounded border px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                {t('cancelButton')}
              </button>
              <button
                onClick={handleResume}
                className="flex-1 rounded bg-amber-500 px-3 py-2 text-sm font-bold text-white hover:bg-amber-400 transition-colors"
              >
                {t('resumeButton')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
