'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { useAuth } from '@/lib/auth'
import {
  getAIFeedbackByDecision,
  recordAIFeedback,
} from '@/lib/api/ai-feedback'
import type { AIFeedbackResponse } from '@/lib/api/ai-feedback'

interface FeedbackSectionProps {
  decisionId: number
}

type ActualOutcome = 'profit' | 'loss' | 'neutral' | 'unknown'

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ja-JP', {
      timeZone: 'Asia/Tokyo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function FeedbackSection({ decisionId }: FeedbackSectionProps) {
  const t = useTranslations('FeedbackSection')
  const { token } = useAuth()

  const [feedbacks, setFeedbacks] = useState<AIFeedbackResponse[]>([])
  const [loadingFeedbacks, setLoadingFeedbacks] = useState(false)
  const [showForm, setShowForm] = useState(false)

  // フォーム状態
  const [isCorrect, setIsCorrect] = useState<boolean | null>(null)
  const [outcome, setOutcome] = useState<ActualOutcome>('unknown')
  const [pnlInput, setPnlInput] = useState('')
  const [suggestion, setSuggestion] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const loadFeedbacks = useCallback(async () => {
    if (!token) return
    setLoadingFeedbacks(true)
    try {
      const data = await getAIFeedbackByDecision(token, decisionId)
      setFeedbacks(data)
    } catch {
      // fail-open: フィードバック取得失敗は表示しない
    } finally {
      setLoadingFeedbacks(false)
    }
  }, [token, decisionId])

  useEffect(() => {
    void loadFeedbacks()
  }, [loadFeedbacks])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!token) return
    setSubmitting(true)
    setSubmitError(null)
    setSuccessMsg(null)
    try {
      const pnlValue = pnlInput.trim() !== '' ? Number(pnlInput) : undefined
      await recordAIFeedback(token, {
        ai_decision_id: decisionId,
        is_correct: isCorrect ?? undefined,
        actual_outcome: outcome,
        pnl_usd: pnlValue,
        improvement_suggestion: suggestion.trim() || undefined,
      })
      setSuccessMsg(t('submitSuccess'))
      // フォームリセット
      setIsCorrect(null)
      setOutcome('unknown')
      setPnlInput('')
      setSuggestion('')
      setShowForm(false)
      void loadFeedbacks()
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : (err as { message?: string })?.message ?? t('submitFailed')
      setSubmitError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const OUTCOME_LABELS: Record<ActualOutcome, string> = {
    profit: t('outcomeProfit'),
    loss: t('outcomeLoss'),
    neutral: t('outcomeNeutral'),
    unknown: t('outcomeUnknown'),
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          {t('sectionTitle')}
        </span>
        <button
          onClick={() => {
            setShowForm((v) => !v)
            setSubmitError(null)
            setSuccessMsg(null)
          }}
          className="text-xs px-2 py-1 rounded bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors"
        >
          {showForm ? t('cancelButton') : t('recordButton')}
        </button>
      </div>

      {/* 成功メッセージ */}
      {successMsg && (
        <div className="mb-2 rounded p-2 text-xs bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300">
          {successMsg}
        </div>
      )}

      {/* フィードバックフォーム */}
      {showForm && (
        <form onSubmit={(e) => void handleSubmit(e)} className="mb-3 space-y-3">
          {/* 結果（正解/不正解） */}
          <div>
            <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
              {t('resultLabel')}
            </label>
            <div className="flex gap-2">
              {[
                { val: true, label: t('correct') },
                { val: false, label: t('incorrect') },
              ].map(({ val, label }) => (
                <button
                  key={String(val)}
                  type="button"
                  onClick={() => setIsCorrect(isCorrect === val ? null : val)}
                  className={`flex-1 py-1.5 text-xs rounded border transition-colors ${
                    isCorrect === val
                      ? val
                        ? 'bg-green-50 dark:bg-green-950 border-green-400 text-green-700 dark:text-green-300'
                        : 'bg-red-50 dark:bg-red-950 border-red-400 text-red-700 dark:text-red-300'
                      : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-gray-400'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* 実績 */}
          <div>
            <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
              {t('outcomeLabel')}
            </label>
            <select
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as ActualOutcome)}
              className="w-full text-xs border border-gray-200 dark:border-gray-700 rounded px-2 py-1.5 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300"
            >
              {(Object.keys(OUTCOME_LABELS) as ActualOutcome[]).map((k) => (
                <option key={k} value={k}>
                  {OUTCOME_LABELS[k]}
                </option>
              ))}
            </select>
          </div>

          {/* 実績損益 USD */}
          <div>
            <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
              {t('pnlLabel')}
            </label>
            <input
              type="number"
              step="0.01"
              value={pnlInput}
              onChange={(e) => setPnlInput(e.target.value)}
              placeholder={t('pnlPlaceholder')}
              className="w-full text-xs border border-gray-200 dark:border-gray-700 rounded px-2 py-1.5 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 placeholder-gray-400"
            />
          </div>

          {/* 改善提案 */}
          <div>
            <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
              {t('suggestionLabel')}
            </label>
            <textarea
              value={suggestion}
              onChange={(e) => setSuggestion(e.target.value)}
              placeholder={t('suggestionPlaceholder')}
              rows={2}
              maxLength={2000}
              className="w-full text-xs border border-gray-200 dark:border-gray-700 rounded px-2 py-1.5 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 placeholder-gray-400 resize-none"
            />
          </div>

          {submitError && (
            <div className="text-xs text-red-600 dark:text-red-400">{submitError}</div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded transition-colors"
          >
            {submitting ? t('submitting') : t('submitButton')}
          </button>
        </form>
      )}

      {/* 既存フィードバック一覧 */}
      {loadingFeedbacks ? (
        <div className="text-xs text-gray-400 dark:text-gray-600 py-2">{t('loading')}</div>
      ) : feedbacks.length === 0 ? (
        <div className="text-xs text-gray-400 dark:text-gray-600 py-2">
          {t('noFeedback')}
        </div>
      ) : (
        <ul className="space-y-2">
          {feedbacks.map((fb) => (
            <li
              key={fb.id}
              className="text-xs bg-gray-50 dark:bg-gray-800 p-2 rounded space-y-1"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-gray-500 dark:text-gray-400">
                  {formatDateTime(fb.recorded_at)}
                </span>
                {fb.is_correct === true && (
                  <span className="text-green-600 dark:text-green-400 font-medium">{t('correct')}</span>
                )}
                {fb.is_correct === false && (
                  <span className="text-red-600 dark:text-red-400 font-medium">{t('incorrect')}</span>
                )}
                <span className="text-gray-600 dark:text-gray-400">
                  {t('outcomeDisplay')}: {OUTCOME_LABELS[fb.actual_outcome] ?? fb.actual_outcome}
                </span>
                {fb.pnl_usd != null && (
                  <span className="text-gray-600 dark:text-gray-400">
                    {t('pnlDisplay')}: ${Number(fb.pnl_usd).toFixed(2)}
                  </span>
                )}
                <span className="ml-auto text-gray-400 dark:text-gray-600">
                  {fb.feedback_source === 'manual'
                    ? t('sourceManual')
                    : fb.feedback_source === 'auto_howl'
                    ? t('sourceAutoHowl')
                    : t('sourceAutoOutcome')}
                </span>
              </div>
              {fb.improvement_suggestion && (
                <p className="text-gray-500 dark:text-gray-400 break-words">
                  💡 {fb.improvement_suggestion}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
