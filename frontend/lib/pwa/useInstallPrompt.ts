'use client'

import { useState, useEffect } from 'react'

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[]
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
  prompt(): Promise<void>
}

export function useInstallPrompt() {
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [isInstalled, setIsInstalled] = useState(false)
  const [isInstallable, setIsInstallable] = useState(false)
  // iOS Safari は beforeinstallprompt 非対応のため isInstallable が立たない。
  // 「共有 → ホーム画面に追加」を案内するため iOS 判定を別途持つ。
  const [isIOS, setIsIOS] = useState(false)

  useEffect(() => {
    // iOS 判定（iPadOS 13+ は UA が Macintosh を名乗るため touch 有無で補完）
    const ua = window.navigator.userAgent
    const iOSDevice =
      /iPad|iPhone|iPod/.test(ua) ||
      (ua.includes('Macintosh') && 'ontouchend' in document)
    setIsIOS(iOSDevice)

    // Check if already installed (standalone mode)
    const mq = window.matchMedia('(display-mode: standalone)')
    setIsInstalled(mq.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true)

    const handleChange = (e: MediaQueryListEvent) => setIsInstalled(e.matches)
    mq.addEventListener('change', handleChange)

    const handleBeforeInstall = (e: Event) => {
      e.preventDefault()
      setPromptEvent(e as BeforeInstallPromptEvent)
      setIsInstallable(true)
    }

    const handleAppInstalled = () => {
      setIsInstalled(true)
      setIsInstallable(false)
      setPromptEvent(null)
    }

    window.addEventListener('beforeinstallprompt', handleBeforeInstall)
    window.addEventListener('appinstalled', handleAppInstalled)

    return () => {
      mq.removeEventListener('change', handleChange)
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall)
      window.removeEventListener('appinstalled', handleAppInstalled)
    }
  }, [])

  const promptInstall = async (): Promise<'accepted' | 'dismissed' | 'unavailable'> => {
    if (!promptEvent) return 'unavailable'
    await promptEvent.prompt()
    const { outcome } = await promptEvent.userChoice
    setPromptEvent(null)
    setIsInstallable(false)
    return outcome
  }

  return { isInstallable, isInstalled, isIOS, promptInstall }
}
