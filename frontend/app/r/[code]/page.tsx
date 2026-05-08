'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'

export default function ReferralRedirectPage() {
  const params = useParams()
  const router = useRouter()
  const code = typeof params.code === 'string' ? params.code : ''

  useEffect(() => {
    if (!code) return
    // Store referral code in cookie for 7 days
    document.cookie = `referral_code=${encodeURIComponent(code)}; max-age=${7 * 24 * 60 * 60}; path=/; SameSite=Lax`
    router.replace(`/auth/register?ref=${encodeURIComponent(code)}`)
  }, [code, router])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">リダイレクト中...</p>
    </div>
  )
}
