// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AuthProvider, useAuth } from '@/lib/auth'
import { getAuthToken } from '@/lib/auth/token-key'

function getRoleDefaultPath(role: string | undefined): string {
  if (role === 'admin') return '/dashboard'
  if ((role as string) === 'partner') return '/partner/dashboard'
  return '/user/dashboard'
}

function RedirectGate() {
  const router = useRouter()
  const { isLoading, isAuthenticated, user } = useAuth()
  const t = useTranslations('RootPage')

  useEffect(() => {
    // LIFF/PWA 消費者アカウント(liff-login経由)は ultra_auth_expires を持たないため
    // useAuth() の isAuthenticated では検出できず、root から /connect へ誤送されていた
    // (実機: staging-v4 rootをそのまま開いたテスターが /liff-chat に着地できなかった不具合)。
    // auth_token の有無を先に見て、あれば useAuth() の初期化完了を待たず /liff-chat へ送る。
    if (getAuthToken()) {
      router.replace('/liff-chat')
      return
    }
    if (isLoading) return
    if (isAuthenticated) {
      router.replace(getRoleDefaultPath(user?.role))
    } else {
      router.replace('/connect')
    }
  }, [isLoading, isAuthenticated, user, router])

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <p className="text-gray-400 text-sm">{t('loading')}</p>
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
