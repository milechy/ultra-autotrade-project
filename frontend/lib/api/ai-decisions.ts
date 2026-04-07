// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/ai-decisions.ts
/**
 * AI判定履歴 API クライアント。
 *
 * バックエンド: GET /api/ai/decisions, GET /api/ai/decisions/{id}, POST /api/ai/trigger
 * スキーマ: backend/app/ai/decisions_schemas.py AIDecisionResponse
 */

import { getJson, postJson } from './http'

// ──────────────────────────────────────────────────────────────────────────────
// Frontend display type (used by all ai-decisions components)
// ──────────────────────────────────────────────────────────────────────────────

export type AiDecision = {
  id: string
  timestamp: string
  query: string
  final_action: 'BUY' | 'SELL' | 'HOLD'
  final_confidence: number
  claude_action: 'BUY' | 'SELL' | 'HOLD'
  claude_confidence: number
  claude_reason: string
  claude_raw_response?: string
  gpt4o_action?: 'BUY' | 'SELL' | 'HOLD'
  gpt4o_confidence?: number
  gpt4o_reason?: string
  gpt4o_raw_response?: string
  agreed: boolean
  rag_context?: { chunks: string[]; query: string; source_count: number }
  executed: boolean
}

// ──────────────────────────────────────────────────────────────────────────────
// Backend response types
// ──────────────────────────────────────────────────────────────────────────────

export interface AIDecisionAPIResponse {
  id: number
  user_id: number | null
  query: string
  /** Final action: BUY / SELL / HOLD */
  action: string
  /** Final confidence 0-100 */
  confidence: number
  /** Primary LLM reason (e.g. Claude) */
  reason: string | null
  primary_provider: string
  primary_action: string
  /** 0-100 */
  primary_confidence: number
  secondary_provider: string | null
  secondary_action: string | null
  /** 0-100 */
  secondary_confidence: number | null
  agreed: boolean
  rag_context_json: unknown
  created_at: string
}

export interface AIDecisionListAPIResponse {
  items: AIDecisionAPIResponse[]
  total: number
  limit: number
  offset: number
}

export interface AITriggerResponse {
  action: string
  /** 0-100 */
  confidence: number
  proposals_created: number
  decision_id: number
}

// ──────────────────────────────────────────────────────────────────────────────
// Mapper: backend → frontend AiDecision
// ──────────────────────────────────────────────────────────────────────────────

type RagContextJSON = {
  chunks?: string[]
  query?: string
  source_count?: number
} | null

function mapDecision(d: AIDecisionAPIResponse): AiDecision {
  const ragCtx = d.rag_context_json as RagContextJSON

  return {
    id: String(d.id),
    timestamp: d.created_at,
    query: d.query,
    final_action: d.action as 'BUY' | 'SELL' | 'HOLD',
    final_confidence: d.confidence / 100,
    claude_action: d.primary_action as 'BUY' | 'SELL' | 'HOLD',
    claude_confidence: d.primary_confidence / 100,
    claude_reason: d.reason ?? '',
    gpt4o_action: d.secondary_action
      ? (d.secondary_action as 'BUY' | 'SELL' | 'HOLD')
      : undefined,
    gpt4o_confidence:
      d.secondary_confidence != null ? d.secondary_confidence / 100 : undefined,
    agreed: d.agreed,
    rag_context:
      ragCtx?.chunks != null
        ? {
            chunks: ragCtx.chunks,
            query: ragCtx.query ?? d.query,
            source_count: ragCtx.source_count ?? ragCtx.chunks.length,
          }
        : undefined,
    executed: false,
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// API functions
// ──────────────────────────────────────────────────────────────────────────────

export interface FetchDecisionsParams {
  page?: number
  limit?: number
  /** 'ALL' はパラメーター送信しない */
  action?: string
  minConfidence?: number
  maxConfidence?: number
  /** undefined は送信しない */
  agreed?: boolean
}

export async function fetchAIDecisions(
  token: string,
  params: FetchDecisionsParams = {}
): Promise<{ items: AiDecision[]; total: number }> {
  const { page = 1, limit = 20, action, minConfidence, maxConfidence, agreed } = params
  const offset = (page - 1) * limit
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (action && action !== 'ALL') q.set('action', action)
  if (minConfidence != null) q.set('min_confidence', String(minConfidence))
  if (maxConfidence != null) q.set('max_confidence', String(maxConfidence))
  if (agreed != null) q.set('agreed', String(agreed))

  const data = await getJson<AIDecisionListAPIResponse>(
    `/api/ai/decisions?${q.toString()}`,
    { headers: { Authorization: `Bearer ${token}` } }
  )
  return { items: data.items.map(mapDecision), total: data.total }
}

export async function fetchAIDecisionDetail(
  token: string,
  id: string
): Promise<AiDecision> {
  const data = await getJson<AIDecisionAPIResponse>(
    `/api/ai/decisions/${id}`,
    { headers: { Authorization: `Bearer ${token}` } }
  )
  return mapDecision(data)
}

/**
 * POST /api/ai/trigger — 管理者専用手動判定実行。
 * body は不要（バックエンドが内部でジョブを実行する）。
 */
export async function triggerAIJudgment(token: string): Promise<AITriggerResponse> {
  return postJson<AITriggerResponse>(
    '/api/ai/trigger',
    {},
    { headers: { Authorization: `Bearer ${token}` } }
  )
}
