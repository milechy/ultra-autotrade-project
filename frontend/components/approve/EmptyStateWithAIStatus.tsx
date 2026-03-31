'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { apiFetch } from '@/lib/api/client'

interface LatestDecision {
  id: number
  action: string
  confidence: number
  reason: string
  created_at: string
}

interface AutomationStatus {
  is_trading_paused: boolean
  next_scheduled_run: string | null
}

function ActionBadge({ action }: { action: string }) {
  if (action === 'BUY') {
    return <Badge className="bg-green-600 hover:bg-green-600 text-white">{action}</Badge>
  }
  if (action === 'SELL') {
    return <Badge className="bg-red-600 hover:bg-red-600 text-white">{action}</Badge>
  }
  return <Badge variant="secondary">{action}</Badge>
}

function formatNextRun(nextRun: string | null): string {
  if (!nextRun) return '計算中'
  const next = new Date(nextRun)
  const now = new Date()
  const diffMs = next.getTime() - now.getTime()
  if (diffMs <= 0) return 'まもなく実行予定'
  const diffHours = Math.round(diffMs / 1000 / 60 / 60)
  if (diffHours < 1) return 'まもなく実行予定'
  return `約${diffHours}時間後（4時間ごとに自動実行）`
}

function formatDate(isoString: string): string {
  const d = new Date(isoString)
  return d.toLocaleString('ja-JP', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function EmptyStateWithAIStatus() {
  const [decision, setDecision] = useState<LatestDecision | null>(null)
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      try {
        const [dec, auto] = await Promise.allSettled([
          apiFetch<LatestDecision>('/api/ai/decisions/latest'),
          apiFetch<AutomationStatus>('/api/automation/status'),
        ])
        if (cancelled) return
        if (dec.status === 'fulfilled') setDecision(dec.value)
        if (auto.status === 'fulfilled') setAutomationStatus(auto.value)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchAll()
    return () => { cancelled = true }
  }, [])

  const showAIStatus = !loading && (decision !== null || automationStatus !== null)

  return (
    <div className="flex flex-col items-center justify-center py-12 gap-4 text-muted-foreground">
      <Clock className="h-10 w-10 opacity-40" />
      <p className="text-sm font-medium">承認待ちの提案はありません</p>

      {loading && (
        <div className="w-full max-w-sm space-y-2">
          <Skeleton className="h-24 rounded-xl" />
        </div>
      )}

      {showAIStatus && (
        <Card className="w-full max-w-sm border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-foreground">AI判定ステータス</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            {decision ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">最新のAI判定</span>
                <div className="flex items-center gap-2">
                  <ActionBadge action={decision.action} />
                  <span className="text-muted-foreground">
                    ({Math.round(decision.confidence * 100)}%)
                  </span>
                  <span className="text-muted-foreground">{formatDate(decision.created_at)}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">最新のAI判定</span>
                <span className="text-muted-foreground">まだAI判定が実行されていません</span>
              </div>
            )}

            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">次回AI判定</span>
              <span className="text-foreground font-medium">
                {formatNextRun(automationStatus?.next_scheduled_run ?? null)}
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-center max-w-sm leading-relaxed">
        AIが市場を分析中です。BUYまたはSELL判定が出た場合に提案が作成されます。
        HOLD判定の場合は提案は作成されません。
      </p>
    </div>
  )
}
