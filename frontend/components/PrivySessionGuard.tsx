'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/components/PrivySessionGuard.tsx
//
// Privy セッションの死活を監視し、JWT は有効だが Privy session が ITP で消えた場合に
// 自動的に Privy 再ログインフローを起動するコンポーネント。
//
// PrivyProvider 配下でのみレンダーすること。
// UserProviders では isPrivyConfigured フラグで条件レンダーしている。

import { useEffect, useRef } from 'react'
import { usePrivy } from '@privy-io/react-auth'
import { useAuth } from '@/lib/auth'

export function PrivySessionGuard() {
  const { isAuthenticated: jwtAuthenticated, isLoading: jwtLoading } = useAuth()
  const { authenticated: privyAuthenticated, ready: privyReady, login } = usePrivy()
  const triggered = useRef(false)

  useEffect(() => {
    // 初期化が完了するまで待つ
    if (jwtLoading || !privyReady) return

    // JWT は有効だが Privy session が消えている → ITP によるセッション消去
    // 一度だけ自動起動し、ループしないよう ref でガード
    if (jwtAuthenticated && !privyAuthenticated && !triggered.current) {
      triggered.current = true
      login()
    }
  }, [jwtAuthenticated, jwtLoading, privyAuthenticated, privyReady, login])

  // このコンポーネントは UI を持たない
  return null
}
