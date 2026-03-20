'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SafetyScoreData } from './types'

interface SafetyScoreProps {
  data: SafetyScoreData
  className?: string
}

type ColorSet = {
  text: string
  bar: string
  bg: string
  border: string
  badge: string
}

function getColorSet(score: number | string): ColorSet {
  const n = Number(score ?? 0)
  if (n >= 80) {
    return {
      text: 'text-green-600',
      bar: 'bg-green-500',
      bg: 'bg-green-50',
      border: 'border-green-200',
      badge: 'bg-green-100 text-green-700 border-green-200',
    }
  }
  if (n >= 50) {
    return {
      text: 'text-yellow-600',
      bar: 'bg-yellow-500',
      bg: 'bg-yellow-50',
      border: 'border-yellow-200',
      badge: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    }
  }
  return {
    text: 'text-red-600',
    bar: 'bg-red-500',
    bg: 'bg-red-50',
    border: 'border-red-200',
    badge: 'bg-red-100 text-red-700 border-red-200',
  }
}

function getJapaneseLabel(score: number | string): string {
  const n = Number(score ?? 0)
  if (n >= 90) return 'とても安全'
  if (n >= 80) return '安全'
  if (n >= 70) return 'やや安全'
  if (n >= 50) return '注意'
  return '危険'
}

export function SafetyScore({ data, className }: SafetyScoreProps) {
  if (!data || typeof data !== 'object') return null
  const [expanded, setExpanded] = useState(false)

  const colors = getColorSet(data.total_score)
  const label = getJapaneseLabel(data.total_score)
  const scoreInt = Math.round(Number(data.total_score ?? 0))

  return (
    <Card className={cn('border', colors.border, colors.bg, className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">安全スコア</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Main score: large number + Japanese label */}
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline gap-2">
            <span className={cn('text-4xl font-bold', colors.text)}>
              {scoreInt}点
            </span>
            <span className={cn('text-xl font-semibold', colors.text)}>
              {label}
            </span>
          </div>
          <p className={cn('text-sm font-medium', colors.text)}>
            {scoreInt}点：{label}
          </p>
          <div className="h-2 w-full rounded-full bg-white/60 overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-500', colors.bar)}
              style={{ width: `${scoreInt}%` }}
            />
          </div>
          {data.summary && (
            <p className="text-sm text-muted-foreground">{data.summary}</p>
          )}
        </div>

        {/* Breakdown toggle */}
        {data.breakdown && data.breakdown.length > 0 && (
          <>
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
                {data.breakdown.map((item) => {
                  const itemColors = getColorSet(item.score)
                  const itemScore = Math.round(Number(item.score ?? 0))
                  return (
                    <div key={item.name} className="flex flex-col gap-1">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span>{item.name}</span>
                          <span className="text-xs text-muted-foreground">
                            (重み {Math.round(item.weight * 100)}%)
                          </span>
                        </div>
                        <span className={cn('font-medium', itemColors.text)}>{itemScore}点</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-white/60 overflow-hidden">
                        <div
                          className={cn('h-full rounded-full transition-all duration-500', itemColors.bar)}
                          style={{ width: `${itemScore}%` }}
                        />
                      </div>
                      {item.description && (
                        <p className="text-xs text-muted-foreground">{item.description}</p>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
