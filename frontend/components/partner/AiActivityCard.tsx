// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/partner/AiActivityCard.tsx
'use client'

import { useTranslations } from 'next-intl'
import { Brain } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useLatestAiDecision } from '@/hooks/useLatestAiDecision'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function actionColor(action: string): string {
  if (action === 'BUY') return 'text-emerald-500 bg-emerald-50 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-400'
  if (action === 'SELL') return 'text-red-500 bg-red-50 border-red-200 dark:bg-red-950/30 dark:border-red-800 dark:text-red-400'
  return 'text-yellow-600 bg-yellow-50 border-yellow-200 dark:bg-yellow-950/30 dark:border-yellow-800 dark:text-yellow-400'
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function AiActivityCard({ className }: { className?: string }) {
  const t = useTranslations('PartnerAiActivityCard')
  const { data, loading, isNewDecision } = useLatestAiDecision()

  function actionLabel(action: string): string {
    if (action === 'BUY') return t('buy')
    if (action === 'SELL') return t('sell')
    return t('hold')
  }

  function formatElapsed(iso: string): string {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
    if (diff < 1) return t('justNow')
    if (diff < 60) return t('minutesAgo', { n: diff })
    return t('hoursAgo', { n: Math.floor(diff / 60) })
  }

  if (loading) {
    return (
      <Card className={cn('overflow-hidden', className)}>
        <CardContent className="p-4 flex items-center gap-4">
          <Skeleton className="h-10 w-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-32 rounded" />
            <Skeleton className="h-3 w-56 rounded" />
          </div>
          <Skeleton className="h-8 w-16 rounded-lg" />
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  const { action, confidence, agreed, reason, created_at } = data
  const reasonSnippet = reason ? reason.split('\n')[0].slice(0, 60) + (reason.length > 60 ? '…' : '') : null

  return (
    <div className={cn('relative overflow-hidden rounded-xl', className)}>
      {/* スキャンアニメーション — 新判定イベント時のみ発火 */}
      {isNewDecision && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-0.5 animate-scan-line z-10 bg-gradient-to-r from-transparent via-blue-400 to-transparent"
        />
      )}

      <Card
        data-testid="ai-activity-card"
        className="border-none shadow-sm"
      >
        <CardContent className="p-4 flex flex-wrap items-center gap-3">
          {/* AI アイコン */}
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950/40">
            <Brain className="h-4 w-4 text-blue-500 dark:text-blue-400" />
          </div>

          {/* 判定バッジ + 情報 */}
          <div className="flex flex-1 flex-wrap items-center gap-2 min-w-0">
            <span
              data-testid="ai-activity-action"
              className={cn(
                'inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-sm font-bold',
                actionColor(action),
              )}
            >
              {action}
              <span className="font-normal text-xs opacity-70">({actionLabel(action)})</span>
            </span>

            <span
              data-testid="ai-activity-confidence"
              className="text-sm font-semibold tabular-nums"
            >
              {confidence}%
            </span>

            {agreed && (
              <span
                data-testid="ai-activity-agreed"
                className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400"
              >
                {t('claudeGptAgreed')}
              </span>
            )}

            {reasonSnippet && (
              <span className="hidden sm:block text-xs text-muted-foreground truncate max-w-xs">
                {reasonSnippet}
              </span>
            )}
          </div>

          {/* 経過時間 */}
          <span
            data-testid="ai-activity-elapsed"
            className="shrink-0 text-xs text-muted-foreground"
          >
            {formatElapsed(created_at)}
          </span>
        </CardContent>
      </Card>
    </div>
  )
}
