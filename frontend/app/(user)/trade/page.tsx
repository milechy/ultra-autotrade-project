'use client'

export const dynamic = 'force-dynamic'

import { useState, useEffect, useCallback } from 'react'
import { CheckCircle, SkipForward, AlertTriangle, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { UserProviders } from '@/components/user/UserProviders'
import { postJson, getJson } from '@/lib/api/http'

type TradeAction = 'BUY' | 'SELL'

type PendingSignal = {
  id: string
  symbol: string
  action: TradeAction
  quantity: string
  estimated_price: string
  confidence: number
  reasoning: string
  created_at: string
}

type ExchangeStatusMin = {
  sandbox_mode: boolean
  shadow_mode?: boolean
}

function ConfirmDialog({
  signal,
  onConfirm,
  onCancel,
  isLoading,
}: {
  signal: PendingSignal
  onConfirm: () => void
  onCancel: () => void
  isLoading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-sm rounded-xl bg-background p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold">取引を承認しますか？</h2>
        <div className="mb-6 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">通貨ペア</span>
            <span className="font-medium">{signal.symbol}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">アクション</span>
            <Badge variant={signal.action === 'BUY' ? 'default' : 'destructive'}>
              {signal.action}
            </Badge>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">数量</span>
            <span className="font-medium">{signal.quantity}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">推定価格</span>
            <span className="font-medium">${parseFloat(signal.estimated_price).toFixed(2)}</span>
          </div>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={onCancel} disabled={isLoading}>
            キャンセル
          </Button>
          <Button
            className="flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
            variant={signal.action === 'BUY' ? 'default' : 'destructive'}
            onClick={onConfirm}
            disabled={true}
          >
            承認して実行
          </Button>
        </div>
      </div>
    </div>
  )
}

function SignalCard({
  signal,
  shadowMode,
  onApprove,
  onSkip,
}: {
  signal: PendingSignal
  shadowMode: boolean
  onApprove: (signal: PendingSignal) => void
  onSkip: (signal: PendingSignal) => void
}) {
  const isBuy = signal.action === 'BUY'
  const createdAt = new Date(signal.created_at).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' })

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            {isBuy ? (
              <TrendingUp className="h-5 w-5 text-green-600" />
            ) : (
              <TrendingDown className="h-5 w-5 text-red-600" />
            )}
            {signal.symbol}
          </CardTitle>
          <Badge variant={isBuy ? 'default' : 'destructive'}>{signal.action}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">{createdAt}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-muted-foreground">数量</span>
            <p className="font-medium">{signal.quantity}</p>
          </div>
          <div>
            <span className="text-muted-foreground">推定価格</span>
            <p className="font-medium">${parseFloat(signal.estimated_price).toFixed(2)}</p>
          </div>
          <div className="col-span-2">
            <span className="text-muted-foreground">信頼度</span>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-2 flex-1 rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${signal.confidence * 100}%` }}
                />
              </div>
              <span className="text-xs font-medium">{Math.round(signal.confidence * 100)}%</span>
            </div>
          </div>
        </div>
        <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
          {signal.reasoning}
        </p>
        {shadowMode && (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              Shadow Mode中は実際の取引は行われません
            </AlertDescription>
          </Alert>
        )}
        <div className="flex gap-2 pt-1">
          <Button
            className="flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
            variant={isBuy ? 'default' : 'destructive'}
            disabled={true}
            onClick={() => onApprove(signal)}
          >
            <CheckCircle className="mr-1 h-4 w-4" />
            承認して実行
          </Button>
          <Button variant="outline" className="flex-1" onClick={() => onSkip(signal)}>
            <SkipForward className="mr-1 h-4 w-4" />
            スキップ
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function TradePage() {
  const { token } = useAuth()
  const [signals, setSignals] = useState<PendingSignal[]>([])
  const [shadowMode, setShadowMode] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isExecuting, setIsExecuting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmTarget, setConfirmTarget] = useState<PendingSignal | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      const [statusData, pendingData] = await Promise.allSettled([
        getJson<ExchangeStatusMin>('/exchange/status', {
          headers: { Authorization: `Bearer ${token}` },
        }),
        getJson<PendingSignal[]>('/ai/pending', {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ])

      if (statusData.status === 'fulfilled') {
        setShadowMode(statusData.value.shadow_mode ?? statusData.value.sandbox_mode ?? false)
      }
      if (pendingData.status === 'fulfilled') {
        setSignals(pendingData.value)
      } else {
        // endpoint may not exist yet — show empty state
        setSignals([])
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '取得エラー')
    } finally {
      setIsLoading(false)
    }
  }, [token])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleApprove = async (signal: PendingSignal) => {
    if (!token) return
    setIsExecuting(true)
    setError(null)
    try {
      await postJson('/exchange/order', {
        signal_id: signal.id,
        symbol: signal.symbol,
        action: signal.action,
        quantity: signal.quantity,
      }, { headers: { Authorization: `Bearer ${token}` } })
      setSignals(prev => prev.filter(s => s.id !== signal.id))
      setSuccessMsg(`${signal.symbol} ${signal.action} を承認しました`)
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '実行エラー'
      setError(`注文エラー: ${msg}`)
    } finally {
      setIsExecuting(false)
      setConfirmTarget(null)
    }
  }

  const handleSkip = async (signal: PendingSignal) => {
    if (!token) return
    setError(null)
    try {
      await postJson('/ai/skip', { signal_id: signal.id }, {
        headers: { Authorization: `Bearer ${token}` },
      })
    } catch {
      // best-effort
    }
    setSignals(prev => prev.filter(s => s.id !== signal.id))
    setSuccessMsg(`${signal.symbol} をスキップしました`)
    setTimeout(() => setSuccessMsg(null), 3000)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="flex items-center justify-between px-4 py-3">
          <h1 className="text-lg font-semibold">取引承認</h1>
          <button
            onClick={fetchData}
            disabled={isLoading}
            className="rounded-full p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-50"
            aria-label="更新"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="space-y-3 px-4 py-4">
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4 flex items-center gap-3">
          <span className="text-amber-600 font-medium">⚠️ Bot売買は現在無効です（Coming Soon）</span>
          <span className="text-amber-500 text-sm">AI判定結果は参考情報として表示しています</span>
        </div>

        {shadowMode && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              Shadow Mode が有効です。承認ボタンは無効化されています。
            </AlertDescription>
          </Alert>
        )}

        {successMsg && (
          <Alert>
            <CheckCircle className="h-4 w-4 text-green-600" />
            <AlertDescription>{successMsg}</AlertDescription>
          </Alert>
        )}

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <RefreshCw className="mb-3 h-8 w-8 animate-spin" />
            <p className="text-sm">読み込み中...</p>
          </div>
        ) : signals.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
            <CheckCircle className="mb-3 h-12 w-12 opacity-30" />
            <p className="text-sm font-medium">承認待ちの取引はありません</p>
            <p className="mt-1 text-xs">AI判定が完了すると、ここに表示されます</p>
          </div>
        ) : (
          signals.map(signal => (
            <SignalCard
              key={signal.id}
              signal={signal}
              shadowMode={shadowMode}
              onApprove={s => setConfirmTarget(s)}
              onSkip={handleSkip}
            />
          ))
        )}
      </div>

      {confirmTarget && (
        <ConfirmDialog
          signal={confirmTarget}
          onConfirm={() => handleApprove(confirmTarget)}
          onCancel={() => setConfirmTarget(null)}
          isLoading={isExecuting}
        />
      )}
    </div>
  )
}

export default function TradeApprovalPage() {
  return (
    <UserProviders>
      <AuthGuard>
        <TradePage />
      </AuthGuard>
    </UserProviders>
  )
}
