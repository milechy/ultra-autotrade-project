'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { LatestDecisionDetail, FactorAnalysis, DecisionTimeline } from './_components'
import { useAuthFetch } from '@/hooks/useAuthFetch'
import { Skeleton } from '@/components/ui/skeleton'

interface AIDecisionResponse {
  id: number
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  reason: string | null
  primary_provider: string
  primary_action: string
  primary_confidence: number
  secondary_provider: string | null
  secondary_action: string | null
  secondary_confidence: number | null
  agreed: boolean
  rag_context_json: unknown
  created_at: string
}

interface AIDecisionListResponse {
  items: AIDecisionResponse[]
  total: number
  limit: number
  offset: number
}

interface Factor {
  score: number
  label: string
}

interface Factors {
  technical: Factor
  macro: Factor
  geopolitical: Factor
  sentiment: Factor
}

const DEFAULT_FACTORS: Factors = {
  technical: { score: 0, label: 'データなし' },
  macro: { score: 0, label: 'データなし' },
  geopolitical: { score: 0, label: 'データなし' },
  sentiment: { score: 0, label: 'データなし' },
}

function extractFactors(ragContextJson: unknown): Factors {
  if (
    ragContextJson !== null &&
    typeof ragContextJson === 'object' &&
    'factors' in ragContextJson &&
    typeof (ragContextJson as Record<string, unknown>).factors === 'object' &&
    (ragContextJson as Record<string, unknown>).factors !== null
  ) {
    const raw = (ragContextJson as Record<string, unknown>).factors as Record<string, unknown>
    const parseEntry = (v: unknown): Factor | null => {
      if (
        v !== null &&
        typeof v === 'object' &&
        'score' in v &&
        'label' in v &&
        typeof (v as Record<string, unknown>).score === 'number' &&
        typeof (v as Record<string, unknown>).label === 'string'
      ) {
        return {
          score: (v as Record<string, unknown>).score as number,
          label: (v as Record<string, unknown>).label as string,
        }
      }
      return null
    }
    const technical = parseEntry(raw.technical)
    const macro = parseEntry(raw.macro)
    const geopolitical = parseEntry(raw.geopolitical)
    const sentiment = parseEntry(raw.sentiment)
    if (technical && macro && geopolitical && sentiment) {
      return { technical, macro, geopolitical, sentiment }
    }
  }
  return DEFAULT_FACTORS
}

export default function DecisionsPage() {
  const { data: latest, loading: latestLoading, error: latestError, refetch: refetchLatest } =
    useAuthFetch<AIDecisionResponse>('/api/ai/decisions/latest')
  const { data: listData, loading: listLoading, error: listError, refetch: refetchList } =
    useAuthFetch<AIDecisionListResponse>('/api/ai/decisions?limit=20')

  const t = useTranslations('Decisions')
  const tCommon = useTranslations('Common')

  const loading = latestLoading || listLoading
  const error = latestError ?? listError
  const history = listData?.items ?? []

  const fetchData = useCallback(() => {
    void refetchLatest()
    void refetchList()
  }, [refetchLatest, refetchList])

  return (
    <>
      <title>{t('aiFeedTitle')} - Ultra AutoTrade</title>

      <div className="space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            {t('aiFeedTitle')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('subtitle')}
          </p>
        </div>

        {loading && (
          <div className="space-y-6">
            <Skeleton className="h-40 rounded-xl" />
            <Skeleton className="h-32 rounded-xl" />
            <Skeleton className="h-64 rounded-xl" />
          </div>
        )}

        {!loading && error && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center space-y-3">
            <p className="text-sm text-red-400">{t('fetchError')}</p>
            <button
              onClick={fetchData}
              className="text-xs text-blue-400 hover:text-blue-300 underline"
            >
              {tCommon('retry')}
            </button>
          </div>
        )}

        {!loading && !error && latest && (
          <>
            {/* Latest decision */}
            <section>
              <LatestDecisionDetail
                decision={{
                  action: latest.action,
                  confidence: latest.confidence,
                  reason: latest.reason ?? '',
                  claudeAction: latest.primary_action,
                  gptAction: latest.secondary_action ?? 'N/A',
                  isAgreed: latest.agreed,
                  timestamp: latest.created_at,
                }}
              />
            </section>

            {/* Factor analysis */}
            <section>
              <FactorAnalysis factors={extractFactors(latest.rag_context_json)} />
            </section>

            {/* Decision timeline */}
            <section>
              <DecisionTimeline
                history={history.map((item) => ({
                  id: String(item.id),
                  action: item.action,
                  confidence: item.confidence,
                  reason: item.reason ?? '',
                  timestamp: item.created_at,
                }))}
              />
            </section>
          </>
        )}
      </div>
    </>
  )
}
