'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { CheckCircle, AlertTriangle, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { TradeActionBadge, ConfidenceBar } from '@/components/shared'
import { cn } from '@/lib/utils'

interface LatestDecision {
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  reason: string
  claudeAction: string
  gptAction: string
  isAgreed: boolean
  timestamp: string
}

interface LatestDecisionDetailProps {
  decision: LatestDecision
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tokyo',
  })
}

export function LatestDecisionDetail({ decision }: LatestDecisionDetailProps) {
  return (
    <Card className="dark:bg-gray-900 dark:border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold text-gray-900 dark:text-gray-100">
          最新AI判定
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Action badge + agreement badge */}
        <div className="flex flex-wrap items-center gap-3">
          <TradeActionBadge action={decision.action} />
          {decision.isAgreed ? (
            <Badge
              variant="outline"
              className="flex items-center gap-1 bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800"
            >
              <CheckCircle className="h-3 w-3" />
              判定一致 ✓
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="flex items-center gap-1 bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800"
            >
              <AlertTriangle className="h-3 w-3" />
              判定不一致（安全のためHOLD）
            </Badge>
          )}
        </div>

        {/* Confidence bar */}
        <ConfidenceBar value={decision.confidence} threshold={70} showLabel />

        {/* Reason */}
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
          {decision.reason}
        </p>

        {/* Model agreement details */}
        <div className="flex gap-4 text-xs text-muted-foreground">
          <span>
            Claude:{' '}
            <span
              className={cn(
                'font-semibold',
                decision.claudeAction === 'BUY'
                  ? 'text-green-600 dark:text-green-400'
                  : decision.claudeAction === 'SELL'
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-gray-600 dark:text-gray-400',
              )}
            >
              {decision.claudeAction}
            </span>
          </span>
          <span>
            GPT-4o:{' '}
            <span
              className={cn(
                'font-semibold',
                decision.gptAction === 'BUY'
                  ? 'text-green-600 dark:text-green-400'
                  : decision.gptAction === 'SELL'
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-gray-600 dark:text-gray-400',
              )}
            >
              {decision.gptAction}
            </span>
          </span>
        </div>

        {/* Timestamp */}
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span>{formatTimestamp(decision.timestamp)}</span>
        </div>
      </CardContent>
    </Card>
  )
}
