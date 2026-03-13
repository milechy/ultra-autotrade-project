'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AuthProvider, useAuth } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'

function AdminGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isAdmin, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    console.log('[AdminGuard] effect:', { isLoading, isAuthenticated, isAdmin });
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/login')
      return
    }
    if (!isAdmin) {
      router.replace('/user/dashboard')
    }
  }, [isLoading, isAuthenticated, isAdmin, router])

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
        <AppShell>{children}</AppShell>
      </AdminGuard>
    </AuthProvider>
  )
}
