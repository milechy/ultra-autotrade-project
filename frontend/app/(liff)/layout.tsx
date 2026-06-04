// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { useLiff } from '@/hooks/useLiff'
import { useLiffAutoReAuth } from '@/hooks/useLiffAutoReAuth'
import { SessionExpiryBanner } from '@/components/SessionExpiryBanner'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'

export default function LiffLayout({ children }: { children: React.ReactNode }) {
  const { isInitialized, error } = useLiff()
  // ITP wipe で auth_token が消えた場合に、LINE 側 idToken を使って
  // 黙って /auth/line を叩き直し、ユーザー操作なしで session を復元する。
  // liff-login 以外の LIFF ページに直接遷移しても復帰できる。
  const reauth = useLiffAutoReAuth()

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-red-400">LIFF初期化エラー: {error}</p>
      </div>
    )
  }

  if (!isInitialized) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-zinc-400">読み込み中...</p>
      </div>
    )
  }

  if (reauth.state === 'reauthing') {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-zinc-400">セッションを復元しています...</p>
      </div>
    )
  }

  return (
    <PrivyRootClient>
      <SessionExpiryBanner loginHref="/liff-login" />
      {children}
    </PrivyRootClient>
  )
}
