// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/hooks/useLatestAiDecision.ts
'use client'

import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api/client'

const POLL_INTERVAL_MS = 60_000

export interface LatestAiDecision {
  id: number
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  agreed: boolean
  reason: string | null
  created_at: string
}

interface UseLatestAiDecisionResult {
  data: LatestAiDecision | null
  loading: boolean
  /** true の間はスキャンアニメーションを発火させる */
  isNewDecision: boolean
}

/**
 * パートナー向け最新 AI 判定を 60 秒間隔でポーリングする hook。
 * 判定 id が変わった瞬間だけ isNewDecision=true になる（アニメーション用）。
 */
export function useLatestAiDecision(): UseLatestAiDecisionResult {
  const [data, setData] = useState<LatestAiDecision | null>(null)
  const [loading, setLoading] = useState(true)
  const [isNewDecision, setIsNewDecision] = useState(false)
  const prevIdRef = useRef<number | null>(null)
  const animTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const result = await apiFetch<LatestAiDecision>('/api/partner/ai-activity')
        setData(result)
        if (prevIdRef.current !== null && prevIdRef.current !== result.id) {
          setIsNewDecision(true)
          if (animTimerRef.current) clearTimeout(animTimerRef.current)
          animTimerRef.current = setTimeout(() => setIsNewDecision(false), 2000)
        }
        prevIdRef.current = result.id
      } catch {
        // 404 (判定なし) や 401 は silent — data=null のまま
      } finally {
        setLoading(false)
      }
    }

    void load()
    const id = setInterval(() => { void load() }, POLL_INTERVAL_MS)
    return () => {
      clearInterval(id)
      if (animTimerRef.current) clearTimeout(animTimerRef.current)
    }
  }, [])

  return { data, loading, isNewDecision }
}
