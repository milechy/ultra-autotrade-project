'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import {
  PortfolioSummary,
  PositionList,
  AssetChart,
  LatestDecision,
  SafetyScore,
} from './_components'

export default function DashboardPage() {
  return (
    <div className="px-4 py-6 max-w-md mx-auto space-y-6">
      {/* Section 1: Portfolio KPIs + Health Factor + Status */}
      <section>
        <PortfolioSummary />
      </section>

      {/* Section 2: Safety Score */}
      <section>
        <SafetyScore />
      </section>

      {/* Section 3: Position List */}
      <section>
        <h2 className="text-sm font-semibold text-zinc-400 mb-3">ポジション一覧</h2>
        <PositionList />
      </section>

      {/* Section 4: Asset Chart */}
      <section>
        <h2 className="text-sm font-semibold text-zinc-400 mb-3">資産推移</h2>
        <AssetChart />
      </section>

      {/* Section 5: Latest AI Decision */}
      <section>
        <h2 className="text-sm font-semibold text-zinc-400 mb-3">最新AI判定</h2>
        <LatestDecision />
      </section>
    </div>
  )
}
