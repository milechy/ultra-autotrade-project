'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { TradeActionBadge, ConfidenceBar } from '@/components/shared'
import { apiFetch } from '@/lib/api/client'

interface AIDecisionResponse {
  id: number
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  reason: string | null
  primary_provider: string
  primary_action: string
  secondary_provider: string | null
  secondary_action: string | null
  agreed: boolean
  created_at: string
}

function formatRelativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (diff < 1) return 'たった今'
  if (diff < 60) return `${diff}分前`
  return `${Math.floor(diff / 60)}時間前`
}

export function LatestDecision() {
  const [decision, setDecision] = useState<AIDecisionResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    apiFetch<AIDecisionResponse>('/api/ai/decisions/latest')
      .then((res) => {
        setDecision(res)
      })
      .catch(() => {
        setError(true)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <Card className="border-zinc-800 bg-zinc-900">
        <CardContent className="p-4 space-y-3">
          <Skeleton className="h-6 w-32 rounded" />
          <Skeleton className="h-4 w-full rounded" />
          <Skeleton className="h-4 w-3/4 rounded" />
        </CardContent>
      </Card>
    )
  }

  if (error || decision === null) {
    return (
      <Card className="border-zinc-800 bg-zinc-900">
        <CardContent className="p-4">
          <p className="text-xs text-zinc-500">判定データを取得できません</p>
        </CardContent>
      </Card>
    )
  }

  const { action, confidence, reason, created_at } = decision

  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TradeActionBadge action={action} />
            <span className="text-xs text-zinc-500">{formatRelativeTime(created_at)}</span>
          </div>
          <Link href="/user/decisions" className="text-xs text-blue-400 hover:text-blue-300">
            詳細を見る →
          </Link>
        </div>
        <ConfidenceBar value={confidence} threshold={70} showLabel />
        <p className="text-xs text-zinc-400 leading-relaxed">{reason ?? ''}</p>
      </CardContent>
    </Card>
  )
}
