'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { TradeActionBadge, ConfidenceBar } from '@/components/shared'

// TODO: Replace with GET /api/ai/latest when backend endpoint is ready
const MOCK_DECISION = {
  action: 'HOLD' as const,
  confidence: 72,
  reason: 'ボラティリティ上昇のため様子見。Health Factorは安全圏内。',
  timestamp: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
}

function formatRelativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (diff < 1) return 'たった今'
  if (diff < 60) return `${diff}分前`
  return `${Math.floor(diff / 60)}時間前`
}

export function LatestDecision() {
  const { action, confidence, reason, timestamp } = MOCK_DECISION

  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TradeActionBadge action={action} />
            <span className="text-xs text-zinc-500">{formatRelativeTime(timestamp)}</span>
          </div>
          <Link href="/user/decisions" className="text-xs text-blue-400 hover:text-blue-300">
            詳細を見る →
          </Link>
        </div>
        <ConfidenceBar value={confidence} threshold={70} showLabel />
        <p className="text-xs text-zinc-400 leading-relaxed">{reason}</p>
      </CardContent>
    </Card>
  )
}
