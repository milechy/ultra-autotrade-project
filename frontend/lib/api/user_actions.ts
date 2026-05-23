// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/user_actions.ts
//
// User action logging helper for the manual (display-only) UI.
//
// 本 helper は manual UI (`/approve` 等) における「実取引を伴わない UI 操作」
// をバックエンドの `user_actions` テーブルに記録するための fetch wrapper です。
//
// TODO(P0-6): backend `POST /api/users/actions` エンドポイントの実装は
// P0-6 (user_actions backend) PR で行います。本ファイルは fetch helper のみ。
// エンドポイント未実装でも UI の主機能が止まらないよう、内部で try/catch + console.warn します。

import { apiPost } from './client'

export type UserActionType =
  | 'manual_approve_click'
  | 'manual_reject_click'
  | 'manual_buy_click'
  | 'manual_sell_click'
  | 'onboarding_step_advance'
  | 'onboarding_completed'

export interface LogUserActionInput {
  action_type: UserActionType | string
  target_type?: string
  target_id?: string | number
  context_json?: Record<string, unknown>
}

export interface UserActionResponse {
  id: number
  action_type: string
  created_at: string
}

/**
 * Log a user UI action to the backend.
 *
 * Failure modes (do not throw):
 *  - endpoint not yet implemented (404 / 405) → console.warn, swallow
 *  - network error → console.warn, swallow
 *  - 4xx/5xx → console.warn, swallow
 *
 * Rationale: manual UI is display-only, so logging is best-effort only.
 * Never block the user-visible UI on a logging call.
 */
export async function logUserAction(
  input: LogUserActionInput,
): Promise<UserActionResponse | null> {
  try {
    const result = await apiPost<UserActionResponse>('/api/users/actions', input)
    return result
  } catch (err) {
    // TODO(P0-6): backend エンドポイント merge 後はこの warn が消えるはず。
    // 残っていたら backend 側の不具合か、フロントの呼び出し誤り。
    console.warn('[user_actions] logUserAction failed (backend may be pending P0-6):', err)
    return null
  }
}
