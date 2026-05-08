'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AuthProvider, useAuth } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import { Toaster } from 'sonner'

function AdminGuard({ children }: { children: React.ReactNode }) {
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
    return <div style={{ padding: 40, textAlign: 'center' }}>読み込み中...</div>
  }
  if (!isAuthenticated || !isAdmin) {
    return null
  }
  return <>{children}</>
}

export function AdminProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AdminGuard>
        <AppShell>
          {children}
          <Toaster position="top-center" richColors />
        </AppShell>
      </AdminGuard>
    </AuthProvider>
  )
}