'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// ホーム画面へのインストール促進バナー（Androidのみ表示）

import { useState } from 'react'
import { Download, X } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useInstallPrompt } from '@/lib/pwa/useInstallPrompt'

const DISMISSED_KEY = 'pwa-install-dismissed'

export function InstallBanner() {
  const t = useTranslations('PwaInstallBanner')
  const { isInstallable, isInstalled, promptInstall } = useInstallPrompt()
  const [dismissed, setDismissed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem(DISMISSED_KEY) === '1'
  })

  if (isInstalled || !isInstallable || dismissed) return null

  const handleInstall = async () => {
    const outcome = await promptInstall()
    if (outcome === 'accepted') setDismissed(true)
  }

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, '1')
    setDismissed(true)
  }

  return (
    <div className="fixed bottom-20 inset-x-4 z-50 rounded-xl border border-zinc-700 bg-zinc-900/95 backdrop-blur p-4 shadow-xl md:max-w-sm md:left-auto md:right-4">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 shrink-0">
          <Download className="h-5 w-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-zinc-100">{t('title')}</p>
          <p className="text-xs text-zinc-400 mt-0.5">{t('description')}</p>
        </div>
        <button
          onClick={handleDismiss}
          className="text-zinc-500 hover:text-zinc-300 shrink-0"
          aria-label={t('dismissAriaLabel')}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex gap-2 mt-3">
        <button
          onClick={handleInstall}
          className="flex-1 rounded-lg bg-blue-600 hover:bg-blue-500 px-3 py-2 text-sm font-medium text-white transition-colors"
        >
          {t('installButton')}
        </button>
        <button
          onClick={handleDismiss}
          className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-400 hover:text-zinc-300 transition-colors"
        >
          {t('laterButton')}
        </button>
      </div>
    </div>
  )
}
