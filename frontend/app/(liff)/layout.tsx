// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { useLiff } from '@/hooks/useLiff'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'

// PoC: LIFF layout に PrivyRootClient を追加。
// LIFF WebView内でPrivy embedded walletが動作するか検証するため。
// 本番統合時は liff-approve ページのみに Privy を付与するか検討する。
function LiffLayoutInner({ children }: { children: React.ReactNode }) {
  const { isInitialized, error } = useLiff()

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

  return <>{children}</>
}

export default function LiffLayout({ children }: { children: React.ReactNode }) {
  return (
    <PrivyRootClient>
      <LiffLayoutInner>{children}</LiffLayoutInner>
    </PrivyRootClient>
  )
}
