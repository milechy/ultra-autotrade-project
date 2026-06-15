// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/notifications.ts
/**
 * 通知設定 API クライアント。
 *
 * エンドポイント:
 *   GET  /api/notifications/settings  — 現在のユーザー通知設定取得
 *   PUT  /api/notifications/settings  — 通知設定更新
 *   POST /api/notifications/push/test — テスト通知送信
 */

import { getJson, putJson, postJson } from './http'

/** 各イベントのON/OFFフラグ。 */
export interface NotificationPreferences {
  /** AI 取引提案通知 */
  ai_proposal: boolean
  /** 取引実行完了通知 */
  execution_complete: boolean
  /** HF 警告通知（無効化不可）*/
  health_factor_warning: boolean
  /** 緊急停止通知（無効化不可）*/
  emergency_stop: boolean
  /** 月次レポート LINE 配信 */
  monthly_report: boolean
  /** システムお知らせ */
  system_notice: boolean
}

/** 通知設定レスポンス / リクエストスキーマ。 */
export interface NotificationSettings {
  line_enabled: boolean
  push_enabled: boolean
  preferences: NotificationPreferences
}

/** GET /api/notifications/settings */
export async function fetchNotificationSettings(token: string): Promise<NotificationSettings> {
  return getJson<NotificationSettings>('/api/notifications/settings', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

/** PUT /api/notifications/settings */
export async function updateNotificationSettings(
  token: string,
  settings: Partial<NotificationSettings>,
): Promise<NotificationSettings> {
  return putJson<NotificationSettings>('/api/notifications/settings', settings, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

/** POST /api/notifications/push/test — テスト通知送信 */
export async function sendTestNotification(
  token: string,
  title?: string,
  body?: string,
): Promise<{ sent: number; line_sent: boolean; status?: string }> {
  return postJson<{ sent: number; line_sent: boolean; status?: string }>(
    '/api/notifications/push/test',
    title || body ? { title, body } : {},
    { headers: { Authorization: `Bearer ${token}` } },
  )
}
