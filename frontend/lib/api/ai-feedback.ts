// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/ai-feedback.ts
/**
 * AI判定フィードバック API クライアント。
 *
 * バックエンド: POST /api/ai/feedback/record,
 *              GET /api/ai/feedback/stats,
 *              GET /api/ai/feedback/{decision_id}
 * スキーマ: backend/app/ai/feedback_models.py
 */

import { getJson, postJson } from './http'

// ──────────────────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────────────────

export interface AIFeedbackStats {
  total_feedbacks: number
  correct_count: number
  incorrect_count: number
  accuracy_rate: number | null
  avg_pnl_usd: string | null
  feedback_by_source: Record<string, number>
}

export interface AIFeedbackResponse {
  id: number
  ai_decision_id: number
  is_correct: boolean | null
  actual_outcome: 'profit' | 'loss' | 'neutral' | 'unknown'
  pnl_usd: string | null
  expected_apy: string | null
  actual_apy: string | null
  improvement_suggestion: string | null
  feedback_source: 'manual' | 'auto_howl' | 'auto_outcome'
  recorded_at: string
  recorded_by: string | null
}

export interface AIFeedbackCreate {
  ai_decision_id: number
  is_correct?: boolean
  actual_outcome: 'profit' | 'loss' | 'neutral' | 'unknown'
  pnl_usd?: number
  expected_apy?: number
  actual_apy?: number
  improvement_suggestion?: string
}

// ──────────────────────────────────────────────────────────────────────────────
// API functions
// ──────────────────────────────────────────────────────────────────────────────

/**
 * GET /api/ai/feedback/stats?days=N
 * days=0 は全期間。デフォルト 30 日。
 */
export async function getAIFeedbackStats(
  token: string,
  days = 30
): Promise<AIFeedbackStats> {
  return getJson<AIFeedbackStats>(`/api/ai/feedback/stats?days=${days}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

/**
 * GET /api/ai/feedback/{decisionId}
 * 指定判定 ID に対するフィードバック一覧を返す（空リスト許容）。
 */
export async function getAIFeedbackByDecision(
  token: string,
  decisionId: number
): Promise<AIFeedbackResponse[]> {
  return getJson<AIFeedbackResponse[]>(`/api/ai/feedback/${decisionId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

/**
 * POST /api/ai/feedback/record
 * 管理者専用フィードバック記録。
 */
export async function recordAIFeedback(
  token: string,
  data: AIFeedbackCreate
): Promise<AIFeedbackResponse> {
  return postJson<AIFeedbackResponse>('/api/ai/feedback/record', data, {
    headers: { Authorization: `Bearer ${token}` },
  })
}
