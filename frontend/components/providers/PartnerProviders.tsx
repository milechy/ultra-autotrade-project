'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AuthProvider, useAuth } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import { AutomationStatusProvider } from '@/components/user/UserProviders'
import { EmergencyStopFloat } from '@/components/shared/EmergencyStopFloat'

function PartnerGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isPartner, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/login')
      return
    }
    if (!isPartner) {
      router.replace('/user/dashboard')
    }
  }, [isLoading, isAuthenticated, isPartner, router])

  if (isLoading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>読み込み中...</div>
  }
  if (!isAuthenticated || !isPartner) {
    return null
  }
  return <>{children}</>
}

export function PartnerProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <PartnerGuard>
        <AutomationStatusProvider>
          <AppShell>{children}</AppShell>
          <EmergencyStopFloat />
        </AutomationStatusProvider>
      </PartnerGuard>
    </AuthProvider>
  )
}
