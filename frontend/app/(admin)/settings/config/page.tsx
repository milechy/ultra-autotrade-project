'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/(admin)/settings/config/page.tsx

import React, { useState } from 'react'
import AuthGuard from '@/components/AuthGuard'
import {
  OperationModeSection,
  AISettingsSection,
  RiskEngineSection,
  NotificationSection,
  APIKeySection,
} from '../_components'
import type {
  AISettings,
  RiskSettings,
  NotificationSettings,
  APIKey,
} from '../_components'

type OperationMode = 'NORMAL' | 'SAFE_MODE' | 'HARD_STOP'

const MOCK_SETTINGS = {
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
    slackWebhookUrl: 'https://hooks.slack.com/services/T000/B000/xxxxxxxxxxxx',
    lineToken: 'Bearer xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    notificationLevel: 'WARNING',
  } satisfies NotificationSettings,
  apiKeys: [
    { name: 'Production Key', createdAt: '2026-03-01', maskedKey: 'sk-...a1b2', status: 'active' },
    { name: 'Staging Key', createdAt: '2026-03-15', maskedKey: 'sk-...c3d4', status: 'active' },
  ] satisfies APIKey[],
}

export default function SettingsPage() {
  return (
    <AuthGuard adminOnly>
      <SettingsContent />
    </AuthGuard>
  )
}

function SettingsContent() {
  const [mode, setMode] = useState<OperationMode>(MOCK_SETTINGS.mode)
  const [aiSettings, setAiSettings] = useState<AISettings>(MOCK_SETTINGS.ai)
  const [riskSettings, setRiskSettings] = useState<RiskSettings>(MOCK_SETTINGS.risk)
  const [notifSettings, setNotifSettings] = useState<NotificationSettings>(
    MOCK_SETTINGS.notifications,
  )
  const [apiKeys, setApiKeys] = useState<APIKey[]>(MOCK_SETTINGS.apiKeys)

  const handleRotate = (keyName: string) => {
    // Phase 1: mock rotation (no-op — key list unchanged)
    console.info('API key rotation requested:', keyName)
  }

  return (
    <>
      <title>システム設定 - Ultra AutoTrade</title>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        <div>
          <h1 className="text-xl font-bold text-gray-100">システム設定</h1>
          <p className="mt-1 text-sm text-gray-500">
            運用モード・AI判定・Risk Engine・通知・APIキーを管理します。
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
      </div>
    </>
  )
}
