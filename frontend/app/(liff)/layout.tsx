// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { useLiff } from '@/hooks/useLiff'
import { PrivyRootClient } from '@/lib/wallet/PrivyRootClient'

export default function LiffLayout({ children }: { children: React.ReactNode }) {
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

  return <PrivyRootClient>{children}</PrivyRootClient>
}
