'use client'

import { AuthProvider } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'

export function AdminProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  )
}
