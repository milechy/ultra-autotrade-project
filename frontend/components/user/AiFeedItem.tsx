// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type AiEvent = {
  timestamp?: string
  action?: string
  confidence?: number
  reasoning?: string
  symbol?: string
  agreed?: boolean          // Claude/GPT-4o 一致フラグ
  primary_action?: string   // Claude判定
  secondary_action?: string // GPT-4o判定
  [k: string]: unknown
}

const actionConfig: Record<string, { label: string; className: string }> = {
  BUY: { label: 'BUY', className: 'bg-green-100 text-green-800 border-green-200' },
  SELL: { label: 'SELL', className: 'bg-red-100 text-red-800 border-red-200' },
  HOLD: { label: 'HOLD', className: 'bg-gray-100 text-gray-700 border-gray-200' },
}

export function AiFeedItem({ event }: { event: AiEvent }) {
  const action = String(event.action ?? 'HOLD').toUpperCase()
  const config = actionConfig[action] ?? { label: action, className: 'bg-gray-100 text-gray-700 border-gray-200' }

  const time = event.timestamp
    ? new Date(event.timestamp).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' })
    : null

  return (
    <Card>
      <CardContent className="pt-3 pb-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn('font-mono text-xs font-bold', config.className)}>
              {config.label}
            </Badge>
            {event.symbol && (
              <span className="text-xs font-mono text-muted-foreground">{String(event.symbol)}</span>
            )}
            {event.agreed === true && (
              <Badge variant="outline" className="text-xs bg-green-100 text-green-800 border-green-200">
                ✓ Claude・GPT一致
              </Badge>
            )}
            {event.agreed === false && (
              <Badge variant="outline" className="text-xs bg-yellow-100 text-yellow-800 border-yellow-200">
                △ 判定相違
              </Badge>
            )}
          </div>
        </div>
        {event.confidence != null && (() => {
          const confidence = Math.round(Number(event.confidence) * 100)
          return (
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>信頼度</span>
                <span>{confidence}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                <div
                  className={cn('h-full rounded-full', confidence >= 70 ? 'bg-green-500' : confidence >= 40 ? 'bg-yellow-500' : 'bg-red-400')}
                  style={{ width: `${confidence}%` }}
                />
              </div>
            </div>
          )
        })()}
        {event.reasoning && (
          <p className="text-xs text-muted-foreground line-clamp-2">{String(event.reasoning)}</p>
        )}
        {time && (
          <p className="text-xs text-muted-foreground">{time}</p>
        )}
      </CardContent>
    </Card>
  )
}
