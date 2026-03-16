'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SafetyScoreData } from './types'

interface SafetyScoreProps {
  data: SafetyScoreData
  className?: string
}

function getScoreColor(score: number | string): string {
  const n = Number(score ?? 0)
  if (n >= 70) return 'text-green-600 dark:text-green-400'
  if (n >= 50) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}

function getBarColor(score: number | string): string {
  const n = Number(score ?? 0)
  if (n >= 70) return 'bg-green-500'
  if (n >= 50) return 'bg-yellow-500'
  return 'bg-red-600'
}

export function SafetyScore({ data, className }: SafetyScoreProps) {
  if (!data || typeof data !== 'object') return null
  const [expanded, setExpanded] = useState(false)

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">安全スコア</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Main score */}
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <span className={cn('text-4xl font-bold', getScoreColor(data.total_score))}>
              {data.total_score}
            </span>
            <span className={cn('text-xl font-semibold', getScoreColor(data.total_score))}>
              {data.grade}
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-500', getBarColor(data.total_score))}
              style={{ width: `${Number(data.total_score ?? 0)}%` }}
            />
          </div>
          <p className="text-sm text-muted-foreground">{data.summary}</p>
        </div>

        {/* Breakdown toggle */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <span>詳細を{expanded ? '閉じる' : '見る'}</span>
          <svg
            className={cn('h-4 w-4 transition-transform duration-200', expanded && 'rotate-180')}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {/* Breakdown items */}
        {expanded && (
          <div className="flex flex-col gap-3">
            {(data.breakdown ?? []).map((item) => (
              <div key={item.name} className="flex flex-col gap-1">
                <div className="flex items-center justify-between text-sm">
                  <span>{item.name}</span>
                  <span className={cn('font-medium', getScoreColor(item.score))}>{item.score}</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn('h-full rounded-full transition-all duration-500', getBarColor(item.score))}
                    style={{ width: `${Number(item.score ?? 0)}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground">{item.description}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
