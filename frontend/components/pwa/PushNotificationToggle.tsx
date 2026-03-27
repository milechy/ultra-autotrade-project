// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

type State = 'loading' | 'unsupported' | 'denied' | 'subscribed' | 'unsubscribed'

export function PushNotificationToggle() {
  const [state, setState] = useState<State>('loading')

  useEffect(() => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setState('unsupported')
      return
    }
    if (Notification.permission === 'denied') {
      setState('denied')
      return
    }
    navigator.serviceWorker.ready.then((reg) => {
      reg.pushManager.getSubscription().then((sub) => {
        setState(sub ? 'subscribed' : 'unsubscribed')
      })
    })
  }, [])

  const subscribe = useCallback(async () => {
    const vapidKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY
    if (!vapidKey) {
      toast.error('VAPID キーが未設定です')
      return
    }
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      })
      const json = sub.toJSON()
      await fetch('/notifications/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: json.endpoint,
          keys: json.keys,
        }),
      })
      setState('subscribed')
      toast.success('プッシュ通知を有効にしました')
    } catch (err) {
      if (Notification.permission === 'denied') {
        setState('denied')
        toast.error('通知がブロックされています。ブラウザの設定から許可してください。')
      } else {
        toast.error('通知の登録に失敗しました')
      }
    }
  }, [])

  const unsubscribe = useCallback(async () => {
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) {
        await fetch(
          `/notifications/push/unsubscribe?endpoint=${encodeURIComponent(sub.endpoint)}`,
          { method: 'DELETE' }
        )
        await sub.unsubscribe()
      }
      setState('unsubscribed')
      toast.success('プッシュ通知を無効にしました')
    } catch {
      toast.error('通知の解除に失敗しました')
    }
  }, [])

  if (state === 'loading') return null
  if (state === 'unsupported') return null

  if (state === 'denied') {
    return (
      <p className="text-xs text-zinc-500">
        通知がブロックされています。ブラウザの設定から許可してください。
      </p>
    )
  }

  return (
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-zinc-100">プッシュ通知</p>
        <p className="text-xs text-zinc-400">
          {state === 'subscribed' ? '有効 — AI判定や承認依頼を受け取ります' : '無効'}
        </p>
      </div>
      <Button
        variant={state === 'subscribed' ? 'outline' : 'default'}
        size="sm"
        onClick={state === 'subscribed' ? unsubscribe : subscribe}
        className={
          state === 'subscribed'
            ? 'border-zinc-600 text-zinc-300 hover:bg-zinc-800'
            : 'bg-blue-600 hover:bg-blue-700 text-white'
        }
      >
        {state === 'subscribed' ? 'OFFにする' : '通知をONにする'}
      </Button>
    </div>
  )
}
