'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useMemo } from 'react'
import AuthGuard from '@/components/AuthGuard'
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

// ─── Spec mock data ────────────────────────────────────────────────────────────

type SpecAction = 'BUY' | 'SELL' | 'HOLD'

const SPEC_MOCK_DECISIONS: AiDecision[] = Array.from({ length: 50 }, (_, i) => {
  const queries = [
    'BTC急落ニュース分析',
    'ETH 2.0アップデート影響',
    'Fed利上げ見送り分析',
    'USDC depeg懸念',
    'Aave V3 TVL急増',
  ]
  const actions: SpecAction[] = ['BUY', 'SELL', 'HOLD']
  const action = actions[i % 3]
  const gptAction = actions[(i + (i % 5 === 0 ? 1 : 0)) % 3]
  const confidence = (50 + (i * 7) % 50) / 100

  return {
    id: 'dec-' + String(i).padStart(3, '0'),
    timestamp: new Date(Date.now() - i * 3600000).toISOString(),
    query: queries[i % 5],
    final_action: action,
    final_confidence: confidence,
    claude_action: action,
    claude_confidence: confidence,
    claude_reason:
      'テクニカル指標とマクロ経済状況を総合的に判断した結果です。',
    claude_raw_response: `{"action":"${action}","confidence":${confidence.toFixed(2)},"reasoning":"..."}`,
    gpt4o_action: gptAction,
    gpt4o_confidence: Math.max(0.3, confidence - 0.05),
    gpt4o_reason: 'クロスバリデーション結果に基づく判定です。',
    gpt4o_raw_response: `{"action":"${gptAction}","confidence":${(confidence - 0.05).toFixed(2)}}`,
    agreed: i % 5 !== 0,
    rag_context:
      i % 3 === 0
        ? {
            query: queries[i % 5],
            chunks: [
              'Knowledge Hub: 関連ニュース3件を参照',
              'マクロ経済レポート1件を参照',
            ],
            source_count: 4,
          }
        : undefined,
    executed: i % 4 === 0,
  }
})

// ─── Helpers ──────────────────────────────────────────────────────────────────

function applyFilters(
  decisions: AiDecision[],
  filters: DecisionFiltersState
): AiDecision[] {
  return decisions.filter((d) => {
    if (filters.action !== 'ALL' && d.final_action !== filters.action) {
      return false
    }
    const pct = d.final_confidence * 100
    if (filters.confidenceRange === '0-50' && pct >= 50) return false
    if (filters.confidenceRange === '50-70' && (pct < 50 || pct >= 70)) return false
    if (filters.confidenceRange === '70-100' && pct < 70) return false
    if (filters.agreeFilter === 'agreed' && !d.agreed) return false
    if (filters.agreeFilter === 'disagreed' && d.agreed) return false
    return true
  })
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
  // TODO: Replace SPEC_MOCK_DECISIONS with GET /api/ai/decisions?page=1&limit=20
  const decisions = SPEC_MOCK_DECISIONS

  const [filters, setFilters] = useState<DecisionFiltersState>({
    action: 'ALL',
    confidenceRange: 'ALL',
    agreeFilter: 'ALL',
  })
  const [page, setPage] = useState(1)
  const [selectedDecision, setSelectedDecision] = useState<AiDecision | null>(null)
  const [showTriggerModal, setShowTriggerModal] = useState(false)

  const filtered = useMemo(
    () => applyFilters(decisions, filters),
    [decisions, filters]
  )

  function handleFilterChange(next: DecisionFiltersState) {
    setFilters(next)
    setPage(1)
  }

  return (
    <>
      <title>AI判定モニター - Ultra AutoTrade</title>

      {/* Page header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
            AI判定モニター
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            マルチLLMによるAI判定の詳細履歴・フィルタリング
          </p>
        </div>
        <button
          onClick={() => setShowTriggerModal(true)}
          className="px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
        >
          手動判定実行
        </button>
      </div>

      {/* KPI cards */}
      <div className="mb-6">
        <DecisionKPIs decisions={decisions} />
      </div>

      {/* Chart + Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <ActionDistributionChart decisions={decisions} />
        <DecisionFilters filters={filters} onChange={handleFilterChange} />
      </div>

      {/* Decision table */}
      <DecisionTable
        decisions={filtered}
        page={page}
        onPageChange={setPage}
        onRowClick={setSelectedDecision}
      />

      {/* Modals */}
      <DecisionDetailModal
        decision={selectedDecision}
        onClose={() => setSelectedDecision(null)}
      />
      <ManualTriggerModal
        open={showTriggerModal}
        onClose={() => setShowTriggerModal(false)}
      />
    </>
  )
}
