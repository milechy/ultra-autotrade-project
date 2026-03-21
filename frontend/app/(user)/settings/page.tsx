// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

export const dynamic = 'force-dynamic'

import { useState } from 'react'
import { useWallet } from '@/hooks/useWallet'
import {
  OperationModeCard,
  RiskSettingsCard,
  NotificationCard,
  LanguageCard,
  WalletInfoCard,
  AppInfoCard,
} from './_components'

type RiskMode = 'conservative' | 'balanced' | 'aggressive'
type NotificationFrequency = 'all' | 'important' | 'emergency'
type Language = 'ja' | 'en'

interface SettingsState {
  isRunning: boolean
  riskMode: RiskMode
  maxSingleTradeUsd: number
  maxDailyTradeUsd: number
  email: string
  notificationFrequency: NotificationFrequency
  language: Language
}

const DEFAULT_SETTINGS: SettingsState = {
  isRunning: true,
  riskMode: 'balanced',
  maxSingleTradeUsd: 500,
  maxDailyTradeUsd: 2000,
  email: '',
  notificationFrequency: 'important',
  language: 'ja',
}

export default function SettingsPage() {
  const { address, chainId, disconnect } = useWallet()
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS)

  const set = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
    // TODO: Save to backend PUT /api/user/settings
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* ヘッダー */}
      <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="px-4 py-3">
          <h1 className="text-lg font-semibold text-zinc-100">設定</h1>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4 pb-24 max-w-2xl mx-auto">
        {/* 1. 運用モード */}
        <OperationModeCard
          isRunning={settings.isRunning}
          onToggle={(value) => set('isRunning', value)}
        />

        {/* 2. リスク設定 */}
        <RiskSettingsCard
          riskMode={settings.riskMode}
          onRiskModeChange={(mode) => set('riskMode', mode)}
          maxSingleTradeUsd={settings.maxSingleTradeUsd}
          onMaxSingleTradeUsdChange={(value) => set('maxSingleTradeUsd', value)}
          maxDailyTradeUsd={settings.maxDailyTradeUsd}
          onMaxDailyTradeUsdChange={(value) => set('maxDailyTradeUsd', value)}
        />

        {/* 3. 通知設定 */}
        <NotificationCard
          email={settings.email}
          onEmailChange={(value) => set('email', value)}
          frequency={settings.notificationFrequency}
          onFrequencyChange={(value) => set('notificationFrequency', value)}
        />

        {/* 4. 言語設定 */}
        <LanguageCard
          language={settings.language}
          onLanguageChange={(value) => set('language', value)}
        />

        {/* 5. ウォレット情報 */}
        <WalletInfoCard
          address={address}
          chainId={chainId}
          onDisconnect={disconnect}
        />

        {/* 6. アプリ情報 */}
        <AppInfoCard />
      </div>
    </div>
  )
}
