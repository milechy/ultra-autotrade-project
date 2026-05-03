// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AuthProvider, useAuth } from '@/lib/auth'

function getRoleDefaultPath(role: string | undefined): string {
  if (role === 'admin') return '/dashboard'
  if ((role as string) === 'partner') return '/partner/dashboard'
  return '/user/dashboard'
}

function RedirectGate() {
  const router = useRouter()
  const { isLoading, isAuthenticated, user } = useAuth()

  useEffect(() => {
    if (isLoading) return
    if (isAuthenticated) {
      router.replace(getRoleDefaultPath(user?.role))
    } else {
      router.replace('/login')
    }
  }, [isLoading, isAuthenticated, user, router])

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <p className="text-gray-400 text-sm">読み込み中...</p>
    </div>
  )
}

export default function RootPage() {
  return (
    <AuthProvider>
      <RedirectGate />
    </AuthProvider>
  )
}
