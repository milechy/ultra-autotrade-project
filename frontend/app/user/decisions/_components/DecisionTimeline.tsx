'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TradeActionBadge } from '@/components/shared'

interface HistoryItem {
  id: string
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  reason: string
  timestamp: string
}

interface DecisionTimelineProps {
  history: HistoryItem[]
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleString('ja-JP', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tokyo',
  })
}

export function DecisionTimeline({ history }: DecisionTimelineProps) {
  const t = useTranslations('Decisions')
  return (
    <Card className="dark:bg-gray-900 dark:border-gray-800">
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-base font-semibold text-gray-900 dark:text-gray-100">
          {t('historyTitle')}
        </CardTitle>
        <Link
          href="/history"
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          {t('viewAllHistory')}
        </Link>
      </CardHeader>
      <CardContent className="p-0">
        <ul className="divide-y divide-gray-100 dark:divide-gray-800">
          {history.map((item) => (
            <li
              key={item.id}
              className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
            >
              {/* Timestamp */}
              <span className="text-xs text-muted-foreground whitespace-nowrap pt-0.5 min-w-[72px]">
                {formatTimestamp(item.timestamp)}
              </span>

              {/* Badge */}
              <div className="pt-0.5 flex-shrink-0">
                <TradeActionBadge action={item.action} />
              </div>

              {/* Confidence */}
              <span className="text-xs font-semibold text-gray-600 dark:text-gray-400 pt-0.5 min-w-[36px]">
                {item.confidence}%
              </span>

              {/* Reason (truncated) */}
              <span className="text-xs text-gray-600 dark:text-gray-400 truncate flex-1 pt-0.5">
                {item.reason}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
