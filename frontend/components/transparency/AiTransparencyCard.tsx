'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { apiFetch } from '@/lib/api/client'
import { cn } from '@/lib/utils'
import { Info } from 'lucide-react'

// ─── Types ───────────────────────────────────────────────────────────────────

interface AIDecisionResponse {
  id: number
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  reason: string | null
  primary_provider: string
  primary_action: string
  primary_confidence: number
  secondary_provider: string | null
  secondary_action: string | null
  secondary_confidence: number | null
  agreed: boolean
  created_at: string
}

interface ParsedMetric {
  label: string
  value: number
  threshold?: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseReasonMetrics(reason: string): ParsedMetric[] {
  const metrics: ParsedMetric[] = []
  // Match patterns like "Indicator 38%", "Macro 25%", "Confidence ≥70%"
  const pctPattern = /([A-Za-zぁ-ん一-龥\s/_]+?)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%/g
  let m: RegExpExecArray | null
  while ((m = pctPattern.exec(reason)) !== null) {
    const label = m[1].trim()
    const value = parseFloat(m[2])
    if (label && !isNaN(value)) {
      metrics.push({ label, value })
    }
  }
  // Extract threshold from patterns like "≥70%" or "両方≥70%"
  const thresholdMatch = reason.match(/[≥>=]\s*(\d+)\s*%/)
  if (thresholdMatch && metrics.length > 0) {
    const threshold = parseInt(thresholdMatch[1])
    metrics.forEach((m2) => { m2.threshold = threshold })
  }
  return metrics
}

function actionColor(action: string): string {
  if (action === 'BUY') return 'text-emerald-400 bg-emerald-950/40 border-emerald-800'
  if (action === 'SELL') return 'text-red-400 bg-red-950/40 border-red-800'
  return 'text-yellow-400 bg-yellow-950/40 border-yellow-800'
}

function actionEmoji(action: string): string {
  if (action === 'BUY') return '📈'
  if (action === 'SELL') return '📉'
  return '⏸️'
}

function actionLabel(action: string): string {
  if (action === 'BUY') return '買い'
  if (action === 'SELL') return '売り'
  return '様子見'
}

function formatRelativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (diff < 1) return 'たった今'
  if (diff < 60) return `${diff}分前`
  return `${Math.floor(diff / 60)}時間前`
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function MetricBar({ label, value, threshold }: ParsedMetric) {
  const pct = Math.min(value, 100)
  const meetsThreshold = threshold != null ? value >= threshold : null

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-400">{label}</span>
        <span
          className={cn(
            'font-semibold',
            meetsThreshold === true
              ? 'text-emerald-400'
              : meetsThreshold === false
              ? 'text-red-400'
              : 'text-zinc-300'
          )}
        >
          {value}%
          {threshold != null && (
            <span className="ml-1 text-zinc-500 font-normal">/ {threshold}% 必要</span>
          )}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            meetsThreshold === true
              ? 'bg-emerald-500'
              : meetsThreshold === false
              ? 'bg-red-500'
              : 'bg-blue-500'
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function AiTransparencyCard({ className }: { className?: string }) {
  const [decision, setDecision] = useState<AIDecisionResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    apiFetch<AIDecisionResponse>('/api/ai/decisions/latest')
      .then(setDecision)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Card className={cn('border-zinc-800 bg-zinc-900', className)}>
        <CardContent className="p-4 space-y-3">
          <Skeleton className="h-8 w-32 rounded" />
          <Skeleton className="h-4 w-full rounded" />
          <Skeleton className="h-4 w-3/4 rounded" />
          <Skeleton className="h-4 w-5/6 rounded" />
        </CardContent>
      </Card>
    )
  }

  if (error || decision === null) {
    return (
      <Card className={cn('border-zinc-800 bg-zinc-900', className)}>
        <CardContent className="p-4">
          <p className="text-xs text-zinc-500">判定データを取得できません</p>
        </CardContent>
      </Card>
    )
  }

  const { action, confidence, reason, primary_provider, secondary_provider, secondary_action, agreed, created_at } = decision
  const metrics = reason ? parseReasonMetrics(reason) : []
  const hasMetrics = metrics.length > 0

  return (
    <Card
      className={cn('border-zinc-800 bg-zinc-900', className)}
      data-testid="ai-transparency-card"
    >
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-sm font-semibold text-zinc-400 flex items-center gap-1.5">
          <Info className="h-3.5 w-3.5" />
          AI 判断の透明性
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-4">

        {/* Action + confidence row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              data-testid="transparency-action-badge"
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-bold',
                actionColor(action)
              )}
            >
              <span>{actionEmoji(action)}</span>
              <span>{action}</span>
              <span className="font-normal text-xs opacity-70">({actionLabel(action)})</span>
            </span>
          </div>
          <div className="text-right">
            <p className="text-xs text-zinc-500">確信度</p>
            <p
              data-testid="transparency-confidence"
              className="text-xl font-bold text-zinc-100"
            >
              {confidence}%
            </p>
          </div>
        </div>

        {/* Confidence bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-zinc-500">
            <span>0%</span>
            <span className="font-medium text-zinc-400">確信度バー</span>
            <span>100%</span>
          </div>
          <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-700',
                confidence >= 70 ? 'bg-emerald-500' : confidence >= 50 ? 'bg-yellow-500' : 'bg-zinc-500'
              )}
              style={{ width: `${Math.min(confidence, 100)}%` }}
            />
          </div>
          <div className="flex justify-end">
            <div className="w-px h-2 bg-zinc-600 relative" style={{ marginLeft: `${70}%` }}>
              <span className="absolute -top-4 -translate-x-1/2 text-[10px] text-zinc-600">70%</span>
            </div>
          </div>
        </div>

        {/* Metrics breakdown */}
        {hasMetrics && (
          <div
            data-testid="transparency-metrics"
            className="space-y-2.5 rounded-lg bg-zinc-800/50 p-3"
          >
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">判断根拠の内訳</p>
            {metrics.map((m, i) => (
              <MetricBar key={i} {...m} />
            ))}
          </div>
        )}

        {/* Raw reason text */}
        {reason && (
          <div
            data-testid="transparency-reason"
            className="rounded-lg bg-zinc-800/30 px-3 py-2.5 border border-zinc-700/50"
          >
            <p className="text-xs text-zinc-500 mb-1">詳細理由</p>
            <p className="text-xs text-zinc-300 leading-relaxed whitespace-pre-wrap">{reason}</p>
          </div>
        )}

        {/* AI agreement */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-xs text-zinc-500">{primary_provider} →</span>
          <span className={cn('text-xs font-medium', actionColor(action).split(' ')[0])}>
            {action}
          </span>
          {secondary_provider && secondary_action && (
            <>
              <span className="text-xs text-zinc-600">|</span>
              <span className="text-xs text-zinc-500">{secondary_provider} →</span>
              <span className={cn('text-xs font-medium', actionColor(secondary_action).split(' ')[0])}>
                {secondary_action}
              </span>
              <span
                data-testid="transparency-agreed"
                className={cn(
                  'ml-auto text-[10px] rounded-full px-2 py-0.5',
                  agreed
                    ? 'bg-emerald-900/50 text-emerald-400'
                    : 'bg-yellow-900/50 text-yellow-400'
                )}
              >
                {agreed ? '両者一致' : '意見相違'}
              </span>
            </>
          )}
          <span className="text-[10px] text-zinc-600 ml-auto">
            {formatRelativeTime(created_at)}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
