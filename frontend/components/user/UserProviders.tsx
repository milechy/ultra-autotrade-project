'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { AuthProvider, useAuth } from '@/lib/auth'
import { SessionExpiryBanner } from '@/components/SessionExpiryBanner'
import { Toaster } from 'sonner'
import { fetchAutomationStatus } from '@/lib/api/automation'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'
import { PrivySessionGuard } from '@/components/PrivySessionGuard'
import type { AutomationStatus } from '@/lib/types'

const isPrivyConfigured =
  !!process.env.NEXT_PUBLIC_PRIVY_APP_ID &&
  process.env.NEXT_PUBLIC_PRIVY_APP_ID !== 'clplaceholder000000000000000000000'

type SystemStatus = 'NORMAL' | 'PAUSED' | 'HARD_STOP'

interface AutomationStatusContextValue {
  systemStatus: SystemStatus
  isStopped: boolean
  refreshStatus: () => Promise<void>
}

const AutomationStatusContext = createContext<AutomationStatusContextValue>({
  systemStatus: 'NORMAL',
  isStopped: false,
  refreshStatus: async () => {},
})

export function useAutomationStatus() {
  return useContext(AutomationStatusContext)
}

function toSystemStatus(s: AutomationStatus): SystemStatus {
  if (s.emergency_reason) return 'HARD_STOP'
  if (s.is_trading_paused) return 'PAUSED'
  return 'NORMAL'
}

/** UserGuard を適用しないパス（Privy オンボーディング経路） */
const GUARD_EXEMPT_PATHS = ['/connect']

function UserGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  const isExempt = GUARD_EXEMPT_PATHS.includes(pathname ?? '')

  useEffect(() => {
    if (isExempt) return
    if (!isLoading && !isAuthenticated) {
      router.replace('/login')
    }
  }, [isLoading, isAuthenticated, router, isExempt])

  if (isLoading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>読み込み中...</div>
  }
  if (!isExempt && !isAuthenticated) {
    return null
  }
  return <>{children}</>
}

export function AutomationStatusProvider({ children }: { children: React.ReactNode }) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>('NORMAL')
  const { token, isLoading } = useAuth()

  const refreshStatus = useCallback(async () => {
    if (isLoading || !token) return
    try {
      const status = await fetchAutomationStatus(token)
      setSystemStatus(toSystemStatus(status))
    } catch {/* keep current on error */}
  }, [isLoading, token])

  useEffect(() => {
    if (isLoading || !token) return
    void refreshStatus()
    const id = setInterval(() => { void refreshStatus() }, 30_000)
    return () => clearInterval(id)
  }, [refreshStatus, isLoading, token])

  const value: AutomationStatusContextValue = {
    systemStatus,
    isStopped: systemStatus === 'HARD_STOP',
    refreshStatus,
  }

  return (
    <AutomationStatusContext.Provider value={value}>
      {children}
    </AutomationStatusContext.Provider>
  )
}

export function UserProviders({ children }: { children: React.ReactNode }) {
  return (
    <PrivyRootClient>
      <AuthProvider>
        <SessionExpiryBanner loginHref="/login" />
        <UserGuard>
          <AutomationStatusProvider>
            <SessionExpiryBanner />
            {isPrivyConfigured && <PrivySessionGuard />}
            {children}
            <Toaster position="top-center" richColors />
          </AutomationStatusProvider>
        </UserGuard>
      </AuthProvider>
    </PrivyRootClient>
  )
}
