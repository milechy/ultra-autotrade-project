'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import {
  DecisionKPIs,
  ActionDistributionChart,
  DecisionFilters,
  DecisionTable,
  DecisionDetailModal,
  ManualTriggerModal,
} from './_components'
import type { DecisionFiltersState } from './_components/DecisionFilters'
import type { AiDecision } from './mock-data'
import {
  fetchAIDecisions,
} from '@/lib/api/ai-decisions'

const PAGE_SIZE = 20

// ─── Filter → API params mapper ───────────────────────────────────────────────

function filtersToApiParams(filters: DecisionFiltersState) {
  let minConfidence: number | undefined
  let maxConfidence: number | undefined
  if (filters.confidenceRange === '0-50') { minConfidence = 0; maxConfidence = 50 }
  else if (filters.confidenceRange === '50-70') { minConfidence = 50; maxConfidence = 70 }
  else if (filters.confidenceRange === '70-100') { minConfidence = 70; maxConfidence = 100 }

  const agreed =
    filters.agreeFilter === 'agreed'
      ? true
      : filters.agreeFilter === 'disagreed'
        ? false
        : undefined

  return {
    action: filters.action === 'ALL' ? undefined : filters.action,
    minConfidence,
    maxConfidence,
    agreed,
  }
}

// ─── Main export ──────────────────────────────────────────────────────────────

export default function AiDecisionsPage() {
  return (
    <AuthGuard adminOnly>
      <AiDecisionsContent />
    </AuthGuard>
  )
}

// ─── Page content ─────────────────────────────────────────────────────────────

function AiDecisionsContent() {
  const t = useTranslations('AdminAiDecisions')
  const { token } = useAuth()

  const [decisions, setDecisions] = useState<AiDecision[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [filters, setFilters] = useState<DecisionFiltersState>({
    action: 'ALL',
    confidenceRange: 'ALL',
    agreeFilter: 'ALL',
  })
  const [page, setPage] = useState(1)
  const [selectedDecision, setSelectedDecision] = useState<AiDecision | null>(null)
  const [showTriggerModal, setShowTriggerModal] = useState(false)

  const load = useCallback(
    async (currentPage: number, currentFilters: DecisionFiltersState) => {
      if (!token) return
      setLoading(true)
      setError(null)
      try {
        const params = filtersToApiParams(currentFilters)
        const result = await fetchAIDecisions(token, {
          page: currentPage,
          limit: PAGE_SIZE,
          ...params,
        })
        setDecisions(result.items)
        setTotal(result.total)
      } catch (err: unknown) {
        const msg =
          err instanceof Error
            ? err.message
            : (err as { message?: string })?.message ?? t('emptyState')
        setError(msg)
      } finally {
        setLoading(false)
      }
    },
    [token, t]
  )

  // 初回ロードとフィルター/ページ変更時に再取得
  useEffect(() => {
    void load(page, filters)
  }, [load, page, filters])

  function handleFilterChange(next: DecisionFiltersState) {
    setFilters(next)
    setPage(1)
  }

  function handlePageChange(next: number) {
    setPage(next)
  }

  // 手動判定後にリフレッシュ
  function handleTriggered() {
    setPage(1)
    void load(1, filters)
  }

  return (
    <>
      <title>{t('pageTitle')}</title>

      {/* Page header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
            {t('heading')}
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t('subheading')}
          </p>
        </div>
        <button
          onClick={() => setShowTriggerModal(true)}
          className="px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
        >
          {t('manualTrigger')}
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && decisions.length === 0 && (
        <div className="mb-6 py-12 text-center text-sm text-gray-400 dark:text-gray-600">
          {t('loading')}
        </div>
      )}

      {/* KPI cards */}
      {decisions.length > 0 && (
        <div className="mb-6">
          <DecisionKPIs decisions={decisions} />
        </div>
      )}

      {/* Chart + Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <ActionDistributionChart decisions={decisions} />
        <DecisionFilters filters={filters} onChange={handleFilterChange} />
      </div>

      {/* Decision table */}
      {!loading && decisions.length === 0 && !error ? (
        <div className="py-16 text-center text-sm text-gray-400 dark:text-gray-600">
          {t('emptyState')}
        </div>
      ) : (
        <DecisionTable
          decisions={decisions}
          page={page}
          onPageChange={handlePageChange}
          onRowClick={setSelectedDecision}
          totalCount={total}
        />
      )}

      {/* Modals */}
      <DecisionDetailModal
        decision={selectedDecision}
        onClose={() => setSelectedDecision(null)}
      />
      <ManualTriggerModal
        open={showTriggerModal}
        onClose={() => setShowTriggerModal(false)}
        onTriggered={handleTriggered}
      />
    </>
  )
}
