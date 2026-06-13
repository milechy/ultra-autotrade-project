// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
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
  const t = useTranslations('PwaNotificationToggle')
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
      toast.error(t('errorVapidKeyMissing'))
      return
    }
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey) as unknown as ArrayBuffer,
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
      toast.success(t('successSubscribed'))
    } catch (err) {
      if (Notification.permission === 'denied') {
        setState('denied')
        toast.error(t('errorBlocked'))
      } else {
        toast.error(t('errorSubscribeFailed'))
      }
    }
  }, [t])

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
      toast.success(t('successUnsubscribed'))
    } catch {
      toast.error(t('errorUnsubscribeFailed'))
    }
  }, [t])

  if (state === 'loading') return null
  if (state === 'unsupported') return null

  if (state === 'denied') {
    return (
      <p className="text-xs text-zinc-500">
        {t('blockedMessage')}
      </p>
    )
  }

  return (
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-zinc-100">{t('labelPushNotification')}</p>
        <p className="text-xs text-zinc-400">
          {state === 'subscribed' ? t('statusEnabled') : t('statusDisabled')}
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
        {state === 'subscribed' ? t('buttonOff') : t('buttonOn')}
      </Button>
    </div>
  )
}
