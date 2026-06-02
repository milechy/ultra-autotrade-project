// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

export const dynamic = 'force-dynamic'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { useWallet } from '@/hooks/useWallet'
import { apiFetch, apiPost, apiPut } from '@/lib/api/client'
import { EmergencyStop } from '@/components/user/EmergencyStop'
import type { AutomationStatus } from '@/lib/types'
import {
  OperationModeCard,
  RiskSettingsCard,
  NotificationCard,
  LanguageCard,
  WalletInfoCard,
  AppInfoCard,
  PasswordChangeCard,
} from './_components'

type RiskMode = 'conservative' | 'balanced' | 'aggressive'
type NotificationFrequency = 'all' | 'important' | 'emergency'
type Language = 'ja' | 'en'

interface RiskModeOption {
  mode: RiskMode
  allowed_in_phase_1: boolean
}

interface UserSettingsResponse {
  notification_email?: string
  notification_frequency?: NotificationFrequency
  max_single_trade_usd?: number
  max_daily_trade_usd?: number
  is_active?: boolean
  user_mode?: string
}

interface SettingsState {
  isRunning: boolean
  riskMode: RiskMode
  maxSingleTradeUsd: number
  maxDailyTradeUsd: number
  email: string
  notificationFrequency: NotificationFrequency
  language: Language
  userMode: string
}

const DEFAULT_SETTINGS: SettingsState = {
  isRunning: true,
  riskMode: 'balanced',
  maxSingleTradeUsd: 500,
  maxDailyTradeUsd: 2000,
  email: '',
  notificationFrequency: 'important',
  language: 'ja',
  userMode: 'managed',
}

export default function SettingsPage() {
  const { token, isAdmin, isPartner } = useAuth()
  const { address, chainId, disconnect } = useWallet()
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS)
  const [isStopped, setIsStopped] = useState(false)
  const [allowedModes, setAllowedModes] = useState<RiskMode[]>(['conservative'])

  // U-07: Load risk mode from GET /auth/risk-mode
  useEffect(() => {
    if (!token) return
    apiFetch<{ mode: RiskMode }>('/auth/risk-mode')
      .then((data) => setSettings((prev) => ({ ...prev, riskMode: data.mode })))
      .catch(() => {/* keep default on error */})
  }, [token])

  // F-10: Load allowed risk modes from GET /auth/risk-modes
  useEffect(() => {
    if (!token) return
    apiFetch<{ modes: RiskModeOption[] }>('/auth/risk-modes')
      .then((data) => {
        const allowed = data.modes
          .filter((m) => m.allowed_in_phase_1)
          .map((m) => m.mode)
        if (allowed.length > 0) setAllowedModes(allowed)
      })
      .catch(() => {/* keep default conservative */})
  }, [token])

  // Load user settings from GET /api/user/settings
  useEffect(() => {
    if (!token) return
    apiFetch<UserSettingsResponse>('/api/user/settings')
      .then((data) => {
        setSettings((prev) => ({
          ...prev,
          ...(data.notification_email !== undefined && { email: data.notification_email }),
          ...(data.notification_frequency !== undefined && { notificationFrequency: data.notification_frequency }),
          ...(data.max_single_trade_usd !== undefined && { maxSingleTradeUsd: data.max_single_trade_usd }),
          ...(data.max_daily_trade_usd !== undefined && { maxDailyTradeUsd: data.max_daily_trade_usd }),
          ...(data.user_mode !== undefined && { userMode: data.user_mode }),
        }))
      })
      .catch(() => {/* keep defaults */})
  }, [token])

  // U-07: Load automation status from GET /api/automation/status (no auth required)
  useEffect(() => {
    apiFetch<AutomationStatus>('/api/automation/status')
      .then((data) => {
        setSettings((prev) => ({ ...prev, isRunning: !data.is_trading_paused }))
        if (data.emergency_reason) setIsStopped(true)
      })
      .catch(() => {/* keep default on error */})
  }, [])

  const set = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))

    // Persist user settings to PUT /api/user/settings
    if (token && (key === 'email' || key === 'notificationFrequency' || key === 'maxSingleTradeUsd' || key === 'maxDailyTradeUsd')) {
      const fieldMap: Partial<Record<keyof SettingsState, string>> = {
        email: 'notification_email',
        notificationFrequency: 'notification_frequency',
        maxSingleTradeUsd: 'max_single_trade_usd',
        maxDailyTradeUsd: 'max_daily_trade_usd',
      }
      const apiKey = fieldMap[key]
      if (apiKey) {
        apiPut('/api/user/settings', { [apiKey]: value }).catch(() => {/* silently ignore */})
      }
    }
  }

  // Connect isRunning toggle to POST /api/user/pause | /api/user/resume
  const handleToggleRunning = (value: boolean) => {
    if (value) {
      apiPost('/api/user/resume', {})
        .then(() => setSettings((prev) => ({ ...prev, isRunning: true })))
        .catch(() => {/* error: keep current state */})
    } else {
      apiPost('/api/user/pause', {})
        .then(() => setSettings((prev) => ({ ...prev, isRunning: false })))
        .catch(() => {/* error: keep current state */})
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* ヘッダー */}
      <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur">
        <div className="px-4 py-3">
          <h1 className="text-lg font-semibold text-zinc-100">設定</h1>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4 pb-24 max-w-4xl mx-auto">
        {/* 1. 運用モード — admin/partner のみ表示（viewer/editor は非表示） */}
        {isPartner && (
          <div data-testid="operation-mode-section">
            <OperationModeCard
              isRunning={settings.isRunning}
              onToggle={handleToggleRunning}
              disabled={isStopped}
              userMode={settings.userMode}
              onModeChange={(mode) => setSettings((prev) => ({ ...prev, userMode: mode }))}
            />
          </div>
        )}

        {/* 2. リスク設定 — admin/partner のみ表示（viewer/editor は非表示） */}
        {isPartner && (
          <div data-testid="risk-settings-section">
            <RiskSettingsCard
              riskMode={settings.riskMode}
              onRiskModeChange={(mode) => set('riskMode', mode)}
              maxSingleTradeUsd={settings.maxSingleTradeUsd}
              onMaxSingleTradeUsdChange={(value) => set('maxSingleTradeUsd', value)}
              maxDailyTradeUsd={settings.maxDailyTradeUsd}
              onMaxDailyTradeUsdChange={(value) => set('maxDailyTradeUsd', value)}
              allowedModes={allowedModes}
            />
          </div>
        )}

        {/* 3. 通知設定 — synced with PUT /api/user/settings */}
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

        {/* 5. ウォレット情報 — admin/partner のみ表示（viewer/tester は非表示） */}
        {isPartner && (
          <WalletInfoCard
            address={address}
            chainId={chainId}
            onDisconnect={disconnect}
          />
        )}

        {/* 6. パスワード変更 */}
        <PasswordChangeCard />

        {/* 7. アプリ情報 */}
        <AppInfoCard />

        {/* U-08: 緊急停止 — POST /api/automation/emergency-stop (admin only) */}
        {isAdmin && (
          <EmergencyStop
            isStopped={isStopped}
            onStopped={() => setIsStopped(true)}
          />
        )}
      </div>
    </div>
  )
}
