'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import dynamic from 'next/dynamic'
import type { FeedbackCountData, SourcePieEntry } from './AILearningChartsRecharts'

// recharts は SSR でクラッシュするため dynamic import + ssr: false が必須
const FeedbackBarChart = dynamic(
  () =>
    import('./AILearningChartsRecharts').then((m) => m.FeedbackBarChart),
  { ssr: false }
)

const SourcePieChart = dynamic(
  () =>
    import('./AILearningChartsRecharts').then((m) => m.SourcePieChart),
  { ssr: false }
)

interface AILearningChartsProps {
  barData: FeedbackCountData[]
  pieData: SourcePieEntry[]
}

export function AILearningCharts({ barData, pieData }: AILearningChartsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      {/* フィードバック件数内訳 */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
          フィードバック件数内訳（30日）
        </h3>
        {barData.some((d) => d.件数 > 0) ? (
          <FeedbackBarChart data={barData} />
        ) : (
          <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
            データなし
          </div>
        )}
      </div>

      {/* フィードバックソース円グラフ */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
          ソース内訳
        </h3>
        {pieData.some((d) => d.value > 0) ? (
          <SourcePieChart data={pieData} />
        ) : (
          <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
            データなし
          </div>
        )}
      </div>
    </div>
  )
}
