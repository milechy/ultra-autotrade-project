'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { AuthProvider, useAuth } from '@/lib/auth'
import { Toaster } from 'sonner'
import { fetchAutomationStatus } from '@/lib/api/automation'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'
import { SessionExpiryBanner } from '@/components/SessionExpiryBanner'
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
        <AutomationStatusProvider>
          <SessionExpiryBanner />
          {isPrivyConfigured && <PrivySessionGuard />}
          {children}
          <Toaster position="top-center" richColors />
        </AutomationStatusProvider>
      </AuthProvider>
    </PrivyRootClient>
  )
}
