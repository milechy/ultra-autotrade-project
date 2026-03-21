'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { LatestDecisionDetail, FactorAnalysis, DecisionTimeline } from './_components'

// TODO: Replace with GET /api/ai/decisions
const MOCK_LATEST = {
  action: 'HOLD' as const,
  confidence: 72,
  reason:
    '現在の市場環境では、主要指標が混在しており、明確なトレンドが確認できません。ボラティリティが落ち着くまでポジション維持を推奨します。',
  claudeAction: 'HOLD',
  gptAction: 'HOLD',
  isAgreed: true,
  timestamp: '2026-03-21T10:30:00Z',
  factors: {
    technical: { score: 0.3, label: 'やや強気' },
    macro: { score: -0.2, label: 'やや弱気' },
    geopolitical: { score: -0.5, label: '弱気' },
    sentiment: { score: 0.4, label: 'やや強気' },
  },
}

const MOCK_HISTORY = [
  {
    id: '1',
    action: 'HOLD' as const,
    confidence: 72,
    reason: 'ボラティリティ継続のためポジション維持',
    timestamp: '2026-03-21T10:30:00Z',
  },
  {
    id: '2',
    action: 'BUY' as const,
    confidence: 81,
    reason: 'USDC supply APR上昇、ポジション増加推奨',
    timestamp: '2026-03-21T04:00:00Z',
  },
  {
    id: '3',
    action: 'HOLD' as const,
    confidence: 68,
    reason: 'マクロ不透明感でHOLD継続',
    timestamp: '2026-03-20T22:00:00Z',
  },
  {
    id: '4',
    action: 'SELL' as const,
    confidence: 75,
    reason: 'HF低下傾向のため一部引き出し推奨',
    timestamp: '2026-03-20T16:00:00Z',
  },
  {
    id: '5',
    action: 'BUY' as const,
    confidence: 85,
    reason: '市場回復シグナル、ETH供給追加推奨',
    timestamp: '2026-03-20T10:00:00Z',
  },
]

export default function DecisionsPage() {
  return (
    <>
      <title>AI判定フィード - Ultra AutoTrade</title>

      <div className="space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            AI判定フィード
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            最新のAI判定結果と判定履歴
          </p>
        </div>

        {/* Latest decision */}
        <section>
          <LatestDecisionDetail decision={MOCK_LATEST} />
        </section>

        {/* Factor analysis */}
        <section>
          <FactorAnalysis factors={MOCK_LATEST.factors} />
        </section>

        {/* Decision timeline */}
        <section>
          <DecisionTimeline history={MOCK_HISTORY} />
        </section>
      </div>
    </>
  )
}
