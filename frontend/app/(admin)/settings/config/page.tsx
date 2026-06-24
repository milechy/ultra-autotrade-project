'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/(admin)/settings/config/page.tsx

import React, { useState } from 'react'
import { useTranslations } from 'next-intl'
import AuthGuard from '@/components/AuthGuard'
import {
  OperationModeSection,
  AISettingsSection,
  RiskEngineSection,
  NotificationSection,
  APIKeySection,
  FeeConfigCard,
} from '../_components'
import type {
  AISettings,
  RiskSettings,
  NotificationSettings,
  APIKey,
} from '../_components'

type OperationMode = 'NORMAL' | 'SAFE_MODE' | 'HARD_STOP'

const DEFAULT_SETTINGS = {
  mode: 'NORMAL' as OperationMode,
  ai: { frequency: '4h', confidenceThreshold: 70, crossVerification: true } satisfies AISettings,
  risk: {
    hfWarning: 1.8,
    hfHardStop: 1.6,
    maxSingleTrade: 10,
    maxDailyTrade: 30,
    cooldownSeconds: 600,
  } satisfies RiskSettings,
  notifications: {
    slackWebhookUrl: '',
    lineToken: '',
    notificationLevel: 'WARNING',
  } satisfies NotificationSettings,
  apiKeys: [] satisfies APIKey[],
}

export default function SettingsPage() {
  return (
    <AuthGuard adminOnly>
      <SettingsContent />
    </AuthGuard>
  )
}

function SettingsContent() {
  const t = useTranslations('AdminSettingsConfig')
  const [mode, setMode] = useState<OperationMode>(DEFAULT_SETTINGS.mode)
  const [aiSettings, setAiSettings] = useState<AISettings>(DEFAULT_SETTINGS.ai)
  const [riskSettings, setRiskSettings] = useState<RiskSettings>(DEFAULT_SETTINGS.risk)
  const [notifSettings, setNotifSettings] = useState<NotificationSettings>(
    DEFAULT_SETTINGS.notifications,
  )
  const [apiKeys, setApiKeys] = useState<APIKey[]>(DEFAULT_SETTINGS.apiKeys)

  const handleRotate = (keyName: string) => {
    // Phase 1: mock rotation (no-op — key list unchanged)
    console.info('API key rotation requested:', keyName)
  }

  return (
    <>
      <title>{t('pageTitle')}</title>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        <div>
          <h1 className="text-xl font-bold text-gray-100">{t('heading')}</h1>
          <p className="mt-1 text-sm text-gray-500">
            {t('subheading')}
          </p>
        </div>

        {/* Section 1: 運用モード */}
        <OperationModeSection mode={mode} onModeChange={setMode} />

        {/* Section 2: AI判定設定 */}
        <AISettingsSection settings={aiSettings} onChange={setAiSettings} />

        {/* Section 3: Risk Engine設定 */}
        <RiskEngineSection settings={riskSettings} onChange={setRiskSettings} />

        {/* Section 4: 通知設定 */}
        <NotificationSection settings={notifSettings} onChange={setNotifSettings} />

        {/* Section 5: APIキー管理 */}
        <APIKeySection apiKeys={apiKeys} onRotate={handleRotate} />

        {/* Section 6: 手数料設定 (F-12) — GET /api/v1/fees/config 参照のみ */}
        <FeeConfigCard />
      </div>
    </>
  )
}
