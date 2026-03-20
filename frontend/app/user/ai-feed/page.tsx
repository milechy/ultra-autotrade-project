'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState } from 'react'
import { LoadingPage } from '@/components/shared/LoadingSpinner'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { AiFeedItem, type AiEvent } from '@/components/user/AiFeedItem'
import { fetchAutomationStatus } from '@/lib/api/automation'
import { useAuth } from '@/lib/auth'
import { Skeleton } from '@/components/ui/skeleton'
import { PerformanceCard } from '@/components/transparency'
import type { PerformanceData } from '@/components/transparency'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function AiFeedContent() {
  const { token } = useAuth()
  const [events, setEvents] = useState<AiEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [performance, setPerformance] = useState<PerformanceData | null>(null)
  const [perfLoading, setPerfLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    const load = async () => {
      try {
        const status = await fetchAutomationStatus(token)
        const raw = (status.recent_events as unknown[]) ?? []
        setEvents(raw as AiEvent[])
        setError(null)
      } catch (e: unknown) {
        const msg = (e as { message?: string })?.message ?? '取得エラー'
        setError(msg)
      } finally {
        setLoading(false)
      }
    }
    // 実績データ（ベストエフォート）
    setPerfLoading(true)
    fetch(`${API_URL}/api/transparency/performance?period_days=30`)
      .then(r => r.json())
      .then(data => setPerformance(data))
      .catch(() => {})
      .finally(() => setPerfLoading(false))
    load()
    const interval = setInterval(load, 60_000)
    return () => clearInterval(interval)
  }, [token])

  if (loading) return <LoadingPage />

  return (
    <div className="space-y-3">
      {/* 実績サマリー */}
      {perfLoading ? (
        <Skeleton className="h-28 w-full rounded-xl" />
      ) : performance ? (
        <PerformanceCard data={performance} />
      ) : null}
      {error && (
        <div className="rounded-md bg-destructive/10 text-destructive px-4 py-2 text-sm">
          {error}
        </div>
      )}
      {events.length === 0 ? (
        <div className="text-center text-muted-foreground text-sm py-16">
          AI判定履歴がありません
        </div>
      ) : (
        events.map((event, i) => <AiFeedItem key={i} event={event} />)
      )}
    </div>
  )
}

export default function AiFeedPage() {
  return (
    <main className="px-4 py-6 max-w-md mx-auto">
      <div className="mb-4">
        <h1 className="text-2xl font-bold">AI判定フィード</h1>
        <p className="text-xs text-muted-foreground mt-1">最新のAI判定結果（60秒更新）</p>
      </div>
      <ErrorBoundary>
        <AiFeedContent />
      </ErrorBoundary>
    </main>
  )
}