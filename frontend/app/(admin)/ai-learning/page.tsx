'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useCallback } from 'react'
import { Brain, CheckCircle, XCircle, TrendingUp } from 'lucide-react'
import { useTranslations } from 'next-intl'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { KPICard } from '@/components/shared/KPICard'
import { AILearningCharts } from './_components/AILearningCharts'
import { getAIFeedbackStats } from '@/lib/api/ai-feedback'
import type { AIFeedbackStats } from '@/lib/api/ai-feedback'

// ─── Main export ──────────────────────────────────────────────────────────────

export default function AILearningPage() {
  return (
    <AuthGuard adminOnly>
      <AILearningContent />
    </AuthGuard>
  )
}

// ─── Page content ─────────────────────────────────────────────────────────────

function AILearningContent() {
  const { token } = useAuth()
  const t = useTranslations('AdminAiLearning')

  const [stats, setStats] = useState<AIFeedbackStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const data = await getAIFeedbackStats(token, 30)
      setStats(data)
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : (err as { message?: string })?.message ?? t('fetchError')
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [token, t])

  useEffect(() => {
    void load()
  }, [load])

  // ── KPI 計算 ──────────────────────────────────────────────────────────────

  const accuracyPct =
    stats?.accuracy_rate != null
      ? `${(stats.accuracy_rate * 100).toFixed(1)}%`
      : t('noData')

  const avgPnl =
    stats?.avg_pnl_usd != null
      ? `$${Number(stats.avg_pnl_usd).toFixed(2)}`
      : t('noData')

  const autoCount =
    stats != null
      ? (stats.feedback_by_source['auto_howl'] ?? 0) +
        (stats.feedback_by_source['auto_outcome'] ?? 0)
      : 0
  const manualCount = stats?.feedback_by_source['manual'] ?? 0
  const sourceRatio =
    stats != null && stats.total_feedbacks > 0
      ? t('sourceRatioValue', { auto: autoCount, manual: manualCount })
      : t('noData')

  // ── チャートデータ ────────────────────────────────────────────────────────

  const barData = [
    { name: t('barTotal'), 件数: stats?.total_feedbacks ?? 0 },
    { name: t('barCorrect'), 件数: stats?.correct_count ?? 0 },
    { name: t('barIncorrect'), 件数: stats?.incorrect_count ?? 0 },
  ]

  const pieData = Object.entries(stats?.feedback_by_source ?? {}).map(
    ([name, value]) => ({ name, value })
  )

  return (
    <>
      <title>{t('pageTitle')}</title>

      {/* ページヘッダー */}
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
          onClick={() => void load()}
          disabled={loading}
          className="px-3 py-1.5 text-sm font-medium bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg transition-colors disabled:opacity-50"
        >
          {loading ? t('loadingLabel') : t('refreshButton')}
        </button>
      </div>

      {/* エラーバナー */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950 p-3 text-sm text-red-700 dark:text-red-300">
          {t('loadErrorPrefix')} {error}
        </div>
      )}

      {/* KPIカード */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPICard
          label={t('kpiAccuracy')}
          value={accuracyPct}
          icon={CheckCircle}
        />
        <KPICard
          label={t('kpiFeedbackTotal')}
          value={stats?.total_feedbacks ?? '—'}
          suffix={t('countSuffix')}
          icon={Brain}
        />
        <KPICard
          label={t('kpiAvgPnl')}
          value={avgPnl}
          icon={TrendingUp}
        />
        <KPICard
          label={t('kpiSourceBreakdown')}
          value={sourceRatio}
          icon={XCircle}
        />
      </div>

      {/* チャート */}
      {loading && !stats ? (
        <div className="py-12 text-center text-sm text-gray-400 dark:text-gray-600">
          {t('loadingLabel')}
        </div>
      ) : (
        <AILearningCharts barData={barData} pieData={pieData} />
      )}

      {/* フィードバック詳細テーブル */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900 mb-6">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
          {t('statsDetailTitle')}
        </h3>
        {stats ? (
          <table className="w-full text-sm">
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              <tr>
                <td className="py-2 text-gray-500 dark:text-gray-400">{t('rowTotalFeedbacks')}</td>
                <td className="py-2 font-medium text-right">{stats.total_feedbacks}{t('countSuffix')}</td>
              </tr>
              <tr>
                <td className="py-2 text-gray-500 dark:text-gray-400">{t('rowCorrect')}</td>
                <td className="py-2 font-medium text-right text-green-600 dark:text-green-400">{stats.correct_count}{t('countSuffix')}</td>
              </tr>
              <tr>
                <td className="py-2 text-gray-500 dark:text-gray-400">{t('rowIncorrect')}</td>
                <td className="py-2 font-medium text-right text-red-600 dark:text-red-400">{stats.incorrect_count}{t('countSuffix')}</td>
              </tr>
              <tr>
                <td className="py-2 text-gray-500 dark:text-gray-400">{t('rowAccuracyRate')}</td>
                <td className="py-2 font-medium text-right">{accuracyPct}</td>
              </tr>
              <tr>
                <td className="py-2 text-gray-500 dark:text-gray-400">{t('rowAvgPnl')}</td>
                <td className="py-2 font-medium text-right">{avgPnl}</td>
              </tr>
              {Object.entries(stats.feedback_by_source).map(([source, count]) => (
                <tr key={source}>
                  <td className="py-2 text-gray-500 dark:text-gray-400">
                    {t('sourcePrefix')}{' '}
                    {source === 'manual'
                      ? t('sourceManual')
                      : source === 'auto_howl'
                      ? t('sourceAutoHowl')
                      : t('sourceAutoOutcome')}
                  </td>
                  <td className="py-2 font-medium text-right">{count}{t('countSuffix')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-600">
            {loading ? t('loadingLabel') : t('noData')}
          </div>
        )}
      </div>

      {/* 最近のフィードバック一覧 */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
          {t('recentFeedbackTitle')}
        </h3>
        <p className="text-xs text-gray-400 dark:text-gray-600">
          {t('recentFeedbackHint')}
        </p>
      </div>
    </>
  )
}
