'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/hooks/useAuthFetch.ts
/**
 * Auth-aware data fetching hook.
 *
 * Lesson learned: useEffect 内で直接 fetch/axios を呼ぶと、認証準備前に
 * リクエストが飛んで 401 が連発する。apiFetch は authReadyPromise で
 * トークン確定を待ってからリクエストするため、このフックを使えば
 * 認証ガードを各コンポーネントで書き忘れる問題を根本解決できる。
 *
 * 内部で apiFetch（@/lib/api/client）を使用:
 * - Bearer トークンを localStorage から自動注入
 * - authReadyPromise で認証完了を待機してからリクエスト
 * - AUTH_SKIP_PATHS は自動的にトークンなしで送信
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api/client'

interface UseAuthFetchOptions {
  /** Set to false to skip automatic fetch on mount (default: true) */
  enabled?: boolean
  /** Polling interval in ms. 0 = disabled (default: 0) */
  refreshInterval?: number
}

interface UseAuthFetchResult<T> {
  data: T | null
  error: Error | null
  loading: boolean
  /** Manually trigger a refetch (e.g. after a mutation or retry button) */
  refetch: () => Promise<void>
}

export function useAuthFetch<T>(
  url: string | null,
  options: UseAuthFetchOptions = {},
): UseAuthFetchResult<T> {
  const { enabled = true, refreshInterval = 0 } = options
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(false)
  const mountedRef = useRef(true)

  const fetchData = useCallback(async () => {
    if (!url || !enabled) return
    setLoading(true)
    setError(null)
    try {
      const result = await apiFetch<T>(url)
      if (mountedRef.current) {
        setData(result)
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err : new Error(String(err)))
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false)
      }
    }
  }, [url, enabled])

  useEffect(() => {
    mountedRef.current = true
    void fetchData()
    return () => {
      mountedRef.current = false
    }
  }, [fetchData])

  useEffect(() => {
    if (refreshInterval <= 0) return
    const id = setInterval(() => { void fetchData() }, refreshInterval)
    return () => clearInterval(id)
  }, [fetchData, refreshInterval])

  return { data, error, loading, refetch: fetchData }
}
