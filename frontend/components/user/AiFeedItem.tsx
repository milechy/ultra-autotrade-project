import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type AiEvent = {
  timestamp?: string
  action?: string
  confidence?: number
  reasoning?: string
  symbol?: string
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
          </div>
          {event.confidence != null && (
            <span className="text-xs text-muted-foreground">
              信頼度 {Math.round(Number(event.confidence) * 100)}%
            </span>
          )}
        </div>
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
