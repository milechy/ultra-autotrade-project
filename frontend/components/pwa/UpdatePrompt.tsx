'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// SW更新検知 → ユーザーにリロード促進

import { useState, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
import { useTranslations } from 'next-intl'

export function UpdatePrompt() {
  const t = useTranslations('PwaUpdatePrompt')
  const [showUpdate, setShowUpdate] = useState(false)

  useEffect(() => {
    const handler = () => setShowUpdate(true)
    window.addEventListener('sw-update-available', handler)
    return () => window.removeEventListener('sw-update-available', handler)
  }, [])

  if (!showUpdate) return null

  return (
    <div className="fixed top-4 inset-x-4 z-50 rounded-xl border border-blue-800 bg-blue-950/95 backdrop-blur p-4 shadow-xl md:max-w-sm md:left-auto md:right-4">
      <div className="flex items-center gap-3">
        <RefreshCw className="h-5 w-5 text-blue-400 shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-blue-100">{t('title')}</p>
          <p className="text-xs text-blue-400 mt-0.5">{t('description')}</p>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="rounded-lg bg-blue-600 hover:bg-blue-500 px-3 py-1.5 text-xs font-medium text-white transition-colors"
        >
          {t('updateButton')}
        </button>
      </div>
    </div>
  )
}
