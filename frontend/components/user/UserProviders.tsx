'use client'

import { AuthProvider } from '@/lib/auth'

export function UserProviders({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}
