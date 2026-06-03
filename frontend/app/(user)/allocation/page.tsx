// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { AllocationPatternCards } from '@/components/proposals/AllocationPatternCards'

export default function AllocationPatternsPage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      {/* ヘッダー */}
      <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="px-4 py-3">
          <h1 className="text-lg font-semibold text-zinc-100">運用パターン</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            運用先配分のパターンを選択してください
          </p>
        </div>
      </div>

      <div className="max-w-4xl px-4 py-4 pb-24 mx-auto">
        <AllocationPatternCards />

        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs text-zinc-500">
            <span className="font-semibold text-zinc-400">現在執行できるのは Conservative のみです。</span>{' '}
            Standard・Aggressive は Base 上の実在運用先で実際に異なる期待 APY / リスクを実 APY 値で示せるようになり次第、内容を更新します。
          </p>
        </div>
      </div>
    </div>
  )
}
