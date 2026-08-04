// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/push/subscription.ts
//
// Web Push 購読の作成・解除ロジック（2026-08-04 PR4）。
//
// 背景: NotificationPanel.tsx の handlePushToggle は OS 通知権限を取得するだけで
// pushManager.subscribe() を一度も呼んでいなかった（購読ゼロの直接原因）。
// 購読作成ロジック自体は components/pwa/PushNotificationToggle.tsx に存在したが、
// どこにもマウントされていなかった。両コンポーネントから共有できるよう本ファイルへ抽出する。
//
// バックエンド (PR3) の /notifications/push/subscribe, /push/unsubscribe は
// require_active_user で認証必須化済み。新規 alias は追加せず既存の正準パスを使う。

import { postJson, deleteJson } from "@/lib/api/http"

export class VapidNotConfiguredError extends Error {
  constructor() {
    super("VAPID public key is not configured")
    this.name = "VapidNotConfiguredError"
  }
}

export class PushSubscribeError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "PushSubscribeError"
  }
}

/** ビルド時に VAPID 公開鍵が設定されているか（トグルの活性・非活性判定に使う）。 */
export function isPushConfigured(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY)
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/")
  const rawData = atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

/** 現在のブラウザ購読 (無ければ null)。Service Worker 非対応環境では常に null。 */
export async function getExistingSubscription(): Promise<PushSubscription | null> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null
  const reg = await navigator.serviceWorker.ready
  return reg.pushManager.getSubscription()
}

/**
 * Push 購読を作成し、バックエンドに登録する。
 *
 * OS 通知権限の取得は呼び出し側の責務（NotificationPanel が Notification.requestPermission
 * を呼んでから本関数を呼ぶ）。VAPID 未設定時は VapidNotConfiguredError を投げる。
 * サーバ登録に失敗した場合はブラウザ側の購読をロールバックする
 * （非カストディアル鍵管理と同型: 片方だけ確定した中途半端な状態を残さない）。
 */
export async function subscribeToPush(token: string): Promise<void> {
  const vapidKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY
  if (!vapidKey) {
    throw new VapidNotConfiguredError()
  }

  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidKey) as unknown as ArrayBuffer,
  })

  const json = sub.toJSON()
  try {
    await postJson(
      "/notifications/push/subscribe",
      { endpoint: json.endpoint, keys: json.keys },
      { headers: { Authorization: `Bearer ${token}` } }
    )
  } catch (e) {
    // サーバ登録失敗 → 付与済みブラウザ購読をロールバック
    try {
      await sub.unsubscribe()
    } catch {
      // ロールバック失敗はログのみ（致命的でない）
      console.warn("[push] subscription rollback failed after server registration error")
    }
    throw new PushSubscribeError(e instanceof Error ? e.message : "subscribe failed")
  }
}

/**
 * Push 購読を解除する。ブラウザ側を先に解除し、その後ベストエフォートで
 * サーバへ通知する（サーバ側通知が失敗しても、失効した購読は次回配信時の
 * 410 検知でいずれ除去される — fail-open）。購読が無ければ何もしない。
 */
export async function unsubscribeFromPush(token: string): Promise<void> {
  const sub = await getExistingSubscription()
  if (!sub) return

  const endpoint = sub.endpoint
  await sub.unsubscribe()

  try {
    await deleteJson(`/notifications/push/unsubscribe?endpoint=${encodeURIComponent(endpoint)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  } catch {
    // サーバ側解除の失敗はログのみ
    console.warn("[push] server-side unsubscribe failed (browser side already unsubscribed)")
  }
}
