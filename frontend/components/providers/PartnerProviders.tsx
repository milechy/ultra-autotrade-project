'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations, NextIntlClientProvider } from 'next-intl'
import { AuthProvider, useAuth } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import { AutomationStatusProvider } from '@/components/user/UserProviders'
import { EmergencyStopFloat } from '@/components/shared/EmergencyStopFloat'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'
import { SessionExpiryBanner } from '@/components/SessionExpiryBanner'
import { Toaster } from 'sonner'
import jaMessages from '@/messages/ja.json'

function PartnerGuardInner({ children }: { children: React.ReactNode }) {
  const t = useTranslations('ProvidersPartner')
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
    return <div style={{ padding: 40, textAlign: 'center' }}>{t('loading')}</div>
  }
  if (!isAuthenticated || !isPartner) {
    return null
  }
  return <>{children}</>
}

function PartnerGuard({ children }: { children: React.ReactNode }) {
  return (
    <NextIntlClientProvider locale="ja" messages={{ ProvidersPartner: jaMessages.ProvidersPartner }}>
      <PartnerGuardInner>{children}</PartnerGuardInner>
    </NextIntlClientProvider>
  )
}

export function PartnerProviders({ children }: { children: React.ReactNode }) {
  return (
    <PrivyRootClient>
      <AuthProvider>
        <SessionExpiryBanner loginHref="/login" />
        <PartnerGuard>
          <AutomationStatusProvider>
            <AppShell>{children}</AppShell>
            <EmergencyStopFloat />
            <Toaster position="top-center" richColors />
          </AutomationStatusProvider>
        </PartnerGuard>
      </AuthProvider>
    </PrivyRootClient>
  )
}
