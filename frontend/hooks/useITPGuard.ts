'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/hooks/useITPGuard.ts
//
// JWT セッション + ITP (last_seen) の状態を監視するフック。
// Privy の検知は PrivySessionGuard コンポーネントが担当し、
// 本フックは usePrivy() を呼ばない（PrivyProvider 非配下でも安全）。

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import {
  updateLastSeen,
  isSessionExpiredByITP,
  isSessionAtRisk,
  getHoursUntilITPExpiry,
} from '@/lib/session/itp-guard'

export type SessionState = 'ok' | 'warning' | 'itp_expired'

export interface ITPGuardResult {
  sessionState: SessionState
  hoursUntilExpiry: number | null
}

function computeState(isAuthenticated: boolean): SessionState {
  if (!isAuthenticated) return 'ok'  // auth.ts が login へ誘導するため here は何もしない
  if (isSessionExpiredByITP()) return 'itp_expired'
  if (isSessionAtRisk()) return 'warning'
  return 'ok'
}

export function useITPGuard(): ITPGuardResult {
  const { isAuthenticated } = useAuth()
  const [sessionState, setSessionState] = useState<SessionState>('ok')
  const [hoursUntilExpiry, setHoursUntilExpiry] = useState<number | null>(null)

  useEffect(() => {
    // 認証済みのみ last_seen を更新 (未認証で書くと初回 incognito で wiped 誤判定)。
    // updateLastSeen 自体も内部で hasActiveToken ガード済 (二重防御)。
    if (isAuthenticated) updateLastSeen()

    function refresh() {
      setSessionState(computeState(isAuthenticated))
      setHoursUntilExpiry(getHoursUntilITPExpiry())
    }

    refresh()

    function onVisibilityChange() {
      if (document.visibilityState === 'visible') {
        if (isAuthenticated) updateLastSeen()
        refresh()
      }
    }

    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [isAuthenticated])

  return { sessionState, hoursUntilExpiry }
}
