'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { AiTransparencyCard } from '@/components/transparency/AiTransparencyCard'

export function LatestDecision() {
  return (
    <div className="space-y-2">
      <AiTransparencyCard />
      <div className="flex justify-end">
        <Link href="/user/decisions" className="text-xs text-blue-400 hover:text-blue-300">
          判定履歴を見る →
        </Link>
      </div>
    </div>
  )
}
