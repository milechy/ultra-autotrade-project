'use client'

import { useEffect, useState } from 'react'
import { LoadingPage } from '@/components/shared/LoadingSpinner'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { AiFeedItem, type AiEvent } from '@/components/user/AiFeedItem'
import { fetchAutomationStatus } from '@/lib/api/automation'
import { useAuth } from '@/lib/auth'

function AiFeedContent() {
  const { token } = useAuth()
  const [events, setEvents] = useState<AiEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const status = await fetchAutomationStatus(token ?? undefined)
        const raw = (status.recent_events as unknown[]) ?? []
        setEvents(raw as AiEvent[])
        setError(null)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : '取得エラー')
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 60_000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <LoadingPage />

  return (
    <div className="space-y-3">
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
