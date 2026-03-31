'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { Brain, BarChart2, Percent } from 'lucide-react'
import { KPICard } from '@/components/shared/KPICard'
import type { AiDecision } from '../mock-data'

interface DecisionKPIsProps {
  decisions: AiDecision[]
}

export function DecisionKPIs({ decisions }: DecisionKPIsProps) {
  const today = new Date().toDateString()
  const todayCount = decisions.filter(
    (d) => new Date(d.timestamp).toDateString() === today
  ).length

  const buyCount = decisions.filter((d) => d.final_action === 'BUY').length
  const sellCount = decisions.filter((d) => d.final_action === 'SELL').length
  const holdCount = decisions.filter((d) => d.final_action === 'HOLD').length
  const total = decisions.length

  const buyPct = total > 0 ? Math.round((buyCount / total) * 100) : 0
  const sellPct = total > 0 ? Math.round((sellCount / total) * 100) : 0
  const holdPct = total > 0 ? Math.round((holdCount / total) * 100) : 0

  const avgConfidence =
    total > 0
      ? Math.round(
          (decisions.reduce((sum, d) => sum + d.final_confidence * 100, 0) / total)
        )
      : 0

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <KPICard
        label="本日の判定数"
        value={todayCount}
        suffix="件"
        icon={Brain}
      />
      <KPICard
        label="BUY/SELL比率"
        value={`BUY ${buyPct}% / SELL ${sellPct}% / HOLD ${holdPct}%`}
        icon={BarChart2}
      />
      <KPICard
        label="平均信頼度"
        value={avgConfidence}
        suffix="%"
        icon={Percent}
      />
    </div>
  )
}
