'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { TradeActionBadge } from '@/components/shared/TradeActionBadge'
import { ConfidenceBar } from '@/components/shared/ConfidenceBar'
import { FeedbackSection } from './FeedbackSection'
import type { AiDecision } from '../mock-data'

interface DecisionDetailModalProps {
  decision: AiDecision | null
  onClose: () => void
}

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

export function DecisionDetailModal({ decision, onClose }: DecisionDetailModalProps) {
  const t = useTranslations('DecisionDetailModal')

  return (
    <Dialog
      open={decision !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700">
        <DialogHeader>
          <DialogTitle className="text-gray-900 dark:text-gray-100">
            {t('title')} — {decision && formatDateTime(decision.timestamp)}
          </DialogTitle>
          <DialogDescription className="text-gray-600 dark:text-gray-400">
            {decision?.query}
          </DialogDescription>
        </DialogHeader>

        {decision && (
          <div className="space-y-4 text-sm">
            {/* Summary row */}
            <div className="flex items-center gap-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-800 flex-wrap">
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400 block mb-1">
                  {t('finalDecision')}
                </span>
                <TradeActionBadge action={decision.final_action} />
              </div>
              <div className="flex-1 min-w-[140px]">
                <ConfidenceBar
                  value={Math.round(decision.final_confidence * 100)}
                  showLabel
                />
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400 block">
                  {t('executed')}
                </span>
                <span
                  className={`font-semibold text-sm ${
                    decision.executed
                      ? 'text-blue-600 dark:text-blue-400'
                      : 'text-gray-400'
                  }`}
                >
                  {decision.executed ? t('executedYes') : t('executedNo')}
                </span>
              </div>
            </div>

            {/* Claude */}
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Claude
                </span>
                <TradeActionBadge action={decision.claude_action} />
                <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
                  {t('claudeConfidence', { pct: Math.round(decision.claude_confidence * 100) })}
                </span>
              </div>
              <p className="text-gray-700 dark:text-gray-300 text-sm">
                {decision.claude_reason}
              </p>
              {decision.claude_raw_response && (
                <details className="mt-2">
                  <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 dark:hover:text-gray-300">
                    {t('rawResponse')}
                  </summary>
                  <pre className="mt-1 text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded overflow-x-auto text-gray-600 dark:text-gray-400">
                    {decision.claude_raw_response}
                  </pre>
                </details>
              )}
            </div>

            {/* GPT-4o */}
            {decision.gpt4o_action && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    GPT-4o
                  </span>
                  <TradeActionBadge action={decision.gpt4o_action} />
                  {decision.gpt4o_confidence != null && (
                    <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
                      {t('gptConfidence', { pct: Math.round(decision.gpt4o_confidence * 100) })}
                    </span>
                  )}
                </div>
                {decision.gpt4o_reason && (
                  <p className="text-gray-700 dark:text-gray-300 text-sm">
                    {decision.gpt4o_reason}
                  </p>
                )}
                {decision.gpt4o_raw_response && (
                  <details className="mt-2">
                    <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 dark:hover:text-gray-300">
                      {t('rawResponse')}
                    </summary>
                    <pre className="mt-1 text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded overflow-x-auto text-gray-600 dark:text-gray-400">
                      {decision.gpt4o_raw_response}
                    </pre>
                  </details>
                )}
              </div>
            )}

            {/* Agreement */}
            <div
              className={`p-2 rounded text-xs font-medium ${
                decision.agreed
                  ? 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300'
                  : 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'
              }`}
            >
              {decision.agreed ? t('agreedMessage') : t('disagreedMessage')}
            </div>

            {/* Feedback section */}
            <FeedbackSection decisionId={parseInt(decision.id, 10)} />

            {/* RAG context */}
            {decision.rag_context && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-2">
                  {t('ragTitle', { count: decision.rag_context.source_count })}
                </span>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  {t('ragQuery', { query: decision.rag_context.query })}
                </p>
                <ul className="space-y-1">
                  {decision.rag_context.chunks.map((chunk, i) => (
                    <li
                      key={i}
                      className="text-xs bg-gray-50 dark:bg-gray-800 p-2 rounded text-gray-600 dark:text-gray-400"
                    >
                      {chunk}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
