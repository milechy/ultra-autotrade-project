'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LoadingPage } from '@/components/shared/LoadingSpinner'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { HealthFactorGauge } from '@/components/shared/HealthFactorGauge'
import { StatusBadge } from '@/components/user/StatusBadge'
import { fetchAutomationStatus } from '@/lib/api/automation'
import type { AutomationStatus } from '@/lib/types'

function DashboardContent() {
  const [autoStatus, setAutoStatus] = useState<AutomationStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const auto = await fetchAutomationStatus()
        setAutoStatus(auto)
        setError(null)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : '取得エラー')
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 30_000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <LoadingPage />

  const hfRaw = autoStatus?.last_health_factor
  const hfNum = hfRaw != null ? parseFloat(String(hfRaw)) : null
  const hf = hfNum != null && !isNaN(hfNum) ? hfNum : null

  const systemStatus = autoStatus?.is_trading_paused
    ? 'HARD_STOP'
    : autoStatus?.last_event_level === 'WARNING'
    ? 'SAFE_MODE'
    : 'NORMAL'

  const statusData = autoStatus as Record<string, unknown> | null
  const shadowMode = Boolean(statusData?.shadow_mode)
  const exchangePhase = statusData?.exchange_phase

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-md bg-destructive/10 text-destructive px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {/* ポートフォリオ概要 */}
      <section>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          ポートフォリオ
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <Card>
            <CardHeader className="pb-1 pt-3 px-3">
              <CardTitle className="text-xs text-muted-foreground">24h 変動</CardTitle>
            </CardHeader>
            <CardContent className="px-3 pb-3">
              {autoStatus?.last_price_change_24h != null ? (
                <p
                  className={`text-2xl font-bold ${
                    autoStatus.last_price_change_24h >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {autoStatus.last_price_change_24h >= 0 ? '+' : ''}
                  {autoStatus.last_price_change_24h.toFixed(2)}%
                </p>
              ) : (
                <p className="text-muted-foreground text-base">—</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-1 pt-3 px-3">
              <CardTitle className="text-xs text-muted-foreground">ステータス</CardTitle>
            </CardHeader>
            <CardContent className="px-3 pb-3 flex items-center">
              <StatusBadge status={systemStatus} />
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Health Factor */}
      <Card>
        <CardContent className="pt-4">
          <HealthFactorGauge value={hf} />
        </CardContent>
      </Card>

      {/* 運用ステータス */}
      <section>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          運用ステータス
        </h2>
        <Card>
          <CardContent className="pt-4 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Shadow Mode</span>
              <Badge
                variant="outline"
                className={`font-mono text-xs ${shadowMode ? 'bg-blue-100 text-blue-800 border-blue-200' : ''}`}
              >
                {shadowMode ? 'ON' : 'OFF'}
              </Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Exchange Phase</span>
              <Badge variant="outline" className="font-mono text-xs">
                {exchangePhase != null ? `Phase ${String(exchangePhase)}` : '—'}
              </Badge>
            </div>
            {autoStatus?.emergency_reason && (
              <div className="rounded-md bg-destructive/10 text-destructive px-3 py-2 text-xs">
                {autoStatus.emergency_reason}
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  )
}

export default function DashboardPage() {
  return (
    <main className="px-4 py-6 max-w-md mx-auto">
      <div className="mb-4">
        <h1 className="text-2xl font-bold">ダッシュボード</h1>
        <p className="text-xs text-muted-foreground mt-1">30秒ごとに自動更新</p>
      </div>
      <ErrorBoundary>
        <DashboardContent />
      </ErrorBoundary>
    </main>
  )
}
