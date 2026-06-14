'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
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

function calcNextRunHours(nextRun: string | null): number | null {
  if (!nextRun) return null
  const next = new Date(nextRun)
  const now = new Date()
  const diffMs = next.getTime() - now.getTime()
  if (diffMs <= 0) return 0
  const diffHours = Math.round(diffMs / 1000 / 60 / 60)
  return diffHours
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
  const t = useTranslations('ApproveEmptyStateAI')
  const [decision, setDecision] = useState<LatestDecision | null>(null)
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null)
  const [loading, setLoading] = useState(true)

  function formatNextRun(nextRun: string | null): string {
    const hours = calcNextRunHours(nextRun)
    if (hours === null) return t('nextRunCalculating')
    if (hours < 1) return t('nextRunSoon')
    return t('nextRunHours', { hours })
  }

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
      <p className="text-sm font-medium">{t('noProposals')}</p>

      {loading && (
        <div className="w-full max-w-sm space-y-2">
          <Skeleton className="h-24 rounded-xl" />
        </div>
      )}

      {showAIStatus && (
        <Card className="w-full max-w-sm border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-foreground">{t('aiStatusTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            {decision ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">{t('labelLatestDecision')}</span>
                <div className="flex items-center gap-2">
                  <ActionBadge action={decision.action} />
                  <span className="text-muted-foreground">
                    ({decision.confidence}%)
                  </span>
                  <span className="text-muted-foreground">{formatDate(decision.created_at)}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">{t('labelLatestDecision')}</span>
                <span className="text-muted-foreground">{t('noDecisionYet')}</span>
              </div>
            )}

            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">{t('labelNextDecision')}</span>
              <span className="text-foreground font-medium">
                {formatNextRun(automationStatus?.next_scheduled_run ?? null)}
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-center max-w-sm leading-relaxed">
        {t('description')}
      </p>
    </div>
  )
}
