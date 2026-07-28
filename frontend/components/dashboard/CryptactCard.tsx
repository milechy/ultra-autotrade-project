'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/dashboard/CryptactCard.tsx

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { FileSpreadsheet, Copy, Check, ExternalLink } from 'lucide-react'
import { useEffectiveWalletAddress } from '@/hooks/useEffectiveWalletAddress'

const CRYPTACT_URL = 'https://www.cryptact.com/'

export function CryptactCard() {
  const t = useTranslations('CryptactCard')
  const { address } = useEffectiveWalletAddress()
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (!address) return
    await navigator.clipboard.writeText(address)
    setCopied(true)
    toast.success(t('copyToast'))
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="h-4 w-4 text-zinc-500" />
        <h2 className="text-sm font-semibold text-zinc-400">{t('title')}</h2>
      </div>

      <p className="text-xs text-zinc-500">{t('description')}</p>

      <ol className="list-decimal list-inside space-y-1 text-xs text-zinc-400">
        <li>{t('step1')}</li>
        <li>{t('step2')}</li>
        <li>{t('step3')}</li>
        <li>{t('step4')}</li>
        <li>{t('step5')}</li>
      </ol>

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => void handleCopy()}
          disabled={!address}
          className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 text-xs font-semibold px-3 py-2 transition-colors"
        >
          {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
          {copied ? t('copied') : t('copyAddress')}
        </button>

        <a
          href={CRYPTACT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-3 py-2 transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
          {t('openCryptact')}
        </a>
      </div>

      {!address && (
        <p className="text-[10px] text-zinc-600">{t('noAddress')}</p>
      )}
    </div>
  )
}
