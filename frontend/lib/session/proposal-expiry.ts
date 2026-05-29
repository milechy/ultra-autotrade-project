// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/lib/session/proposal-expiry.ts
//
// pending proposals の frontend 側期限切れ検知。
// backend は expires_at を設定済み。frontend はその値を二重確認し、
// 期限切れになったら onProposalExpired hook を呼ぶ。
//
// backend の expire ロジックは #461/policy 担当。本ファイルは触らない。

export const PROPOSAL_EXPIRE_DAYS = 7

/**
 * API が返す expires_at (ISO 8601 文字列) がすでに過ぎているか。
 */
export function isProposalExpired(expiresAt: string): boolean {
  try {
    return Date.now() >= new Date(expiresAt).getTime()
  } catch {
    return false
  }
}

/**
 * 期限切れ proposal の通知 hook。
 * P0-10 の LINE 通知実装が来たらここを埋める。
 * 現時点は console.warn でマーキングのみ。
 */
export function onProposalExpired(proposalId: string | number): void {
  // TODO(P0-10): LINE通知 API を呼ぶ
  if (process.env.NODE_ENV !== 'production') {
    console.warn(`[proposal-expiry] proposal ${proposalId} expired without approval`)
  }
}

/**
 * 未承認 proposals のリストから期限切れをフィルタし、
 * 期限切れ分ごとに onProposalExpired を呼ぶ。
 * Returns { active, expired }.
 */
export function partitionProposals<T extends { id: string | number; expiresAt: string }>(
  proposals: T[],
): { active: T[]; expired: T[] } {
  const active: T[] = []
  const expired: T[] = []
  for (const p of proposals) {
    if (isProposalExpired(p.expiresAt)) {
      expired.push(p)
      onProposalExpired(p.id)
    } else {
      active.push(p)
    }
  }
  return { active, expired }
}
