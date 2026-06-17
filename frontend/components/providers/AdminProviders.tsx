'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations, NextIntlClientProvider } from 'next-intl'
import { AuthProvider, useAuth } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import { SessionExpiryBanner } from '@/components/SessionExpiryBanner'
import { Toaster } from 'sonner'
import jaMessages from '@/messages/ja.json'

function AdminGuardInner({ children }: { children: React.ReactNode }) {
  const t = useTranslations('ProvidersAdmin')
  const { isAuthenticated, isAdmin, isPartner, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/login')
      return
    }
    if (!isAdmin) {
      router.replace(isPartner ? '/partner/dashboard' : '/user/dashboard')
    }
  }, [isLoading, isAuthenticated, isAdmin, isPartner, router])

  if (isLoading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>{t('loading')}</div>
  }
  if (!isAuthenticated || !isAdmin) {
    return null
  }
  return <>{children}</>
}

function AdminGuard({ children }: { children: React.ReactNode }) {
  return (
    <NextIntlClientProvider locale="ja" messages={{ ProvidersAdmin: jaMessages.ProvidersAdmin }}>
      <AdminGuardInner>{children}</AdminGuardInner>
    </NextIntlClientProvider>
  )
}

export function AdminProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <NextIntlClientProvider locale="ja" messages={{ SharedSessionExpiry: jaMessages.SharedSessionExpiry }}>
        <SessionExpiryBanner loginHref="/login" />
      </NextIntlClientProvider>
      <AdminGuard>
        <AppShell>
          {children}
          <Toaster position="top-center" richColors />
        </AppShell>
      </AdminGuard>
    </AuthProvider>
  )
}