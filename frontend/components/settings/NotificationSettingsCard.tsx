// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'
/**
 * NotificationSettingsCard — LINE Push 通知設定カード（GID 1215698091517000）
 *
 * 各イベントのON/OFF トグル・LINE 連携状態・テスト送信ボタンを提供する。
 * GET /api/notifications/settings → PUT /api/notifications/settings と連携。
 *
 * i18n: Liff.panels.notification.* キー使用（英語ハードコード禁止）。
 * 認証: token 必須（未認証の場合は null 表示でガード）。
 */

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { Bell, CheckCircle2, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  fetchNotificationSettings,
  updateNotificationSettings,
  sendTestNotification,
  type NotificationSettings,
} from '@/lib/api/notifications'

interface NotificationSettingsCardProps {
  /** ログイン中ユーザーの JWT トークン。未認証時は null。 */
  token: string | null
  /** LINE ログインユーザーかどうか（LINE ID が取得済みなら true）。 */
  isLineUser: boolean
}

const DEFAULT_SETTINGS: NotificationSettings = {
  line_enabled: true,
  push_enabled: false,
  preferences: {
    ai_proposal: true,
    execution_complete: true,
    health_factor_warning: true,
    emergency_stop: true,
    monthly_report: true,
    system_notice: true,
  },
}

export function NotificationSettingsCard({
  token,
  isLineUser,
}: NotificationSettingsCardProps) {
  const t = useTranslations('Liff.panels.notification')

  const [settings, setSettings] = useState<NotificationSettings>(DEFAULT_SETTINGS)
  const [isLoading, setIsLoading] = useState(true)
  const [isSending, setIsSending] = useState(false)

  const loadSettings = useCallback(async () => {
    if (!token) {
      setIsLoading(false)
      return
    }
    try {
      const data = await fetchNotificationSettings(token)
      setSettings(data)
    } catch {
      // フェッチ失敗はデフォルト表示で継続（fail-open）
    } finally {
      setIsLoading(false)
    }
  }, [token])

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  const handleToggle = async (
    field: keyof NotificationSettings['preferences'] | 'line_enabled' | 'push_enabled',
    value: boolean,
  ) => {
    if (!token) return

    // emergency_stop は常に true（変更不可）
    if (field === 'emergency_stop') return
    // health_factor_warning も安全上 true 固定
    if (field === 'health_factor_warning') return

    // optimistic update — 変更前の状態をキャプチャしてロールバック用に保持
    const previous = settings
    const next: NotificationSettings =
      field === 'line_enabled' || field === 'push_enabled'
        ? { ...settings, [field]: value }
        : {
            ...settings,
            preferences: { ...settings.preferences, [field]: value },
          }
    setSettings(next)

    try {
      await updateNotificationSettings(token, next)
    } catch {
      // API 失敗 → 変更前状態にロールバック
      setSettings(previous)
      toast.error(t('saveError'))
    }
  }

  const handleTestNotification = async () => {
    if (!token || isSending) return
    setIsSending(true)
    try {
      await sendTestNotification(token)
      toast.success(t('testNotificationSent'))
    } catch {
      toast.error(t('testNotificationError'))
    } finally {
      setIsSending(false)
    }
  }

  if (!token) return null

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Bell className="h-4 w-4 text-muted-foreground" />
          {t('title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* チャンネル */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t('channelSection')}
          </p>

          {/* LINE 通知 */}
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{t('lineNotification')}</p>
              {isLineUser && (
                <Badge variant="secondary" className="text-xs gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  {t('lineConnected')}
                </Badge>
              )}
            </div>
            <Switch
              checked={settings.line_enabled}
              onCheckedChange={(v) => { void handleToggle('line_enabled', v) }}
              disabled={!isLineUser}
              aria-label={t('lineNotification')}
            />
          </div>

          {/* PWA プッシュ通知 */}
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">{t('pushNotification')}</p>
              <p className="text-xs text-muted-foreground">
                {settings.push_enabled ? t('pushGranted') : t('pushNotGranted')}
              </p>
            </div>
            <Switch
              checked={settings.push_enabled}
              onCheckedChange={(v) => { void handleToggle('push_enabled', v) }}
              aria-label={t('pushNotification')}
            />
          </div>
        </div>

        {/* AI・取引 */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t('aiTradeSection')}
          </p>
          <ToggleRow
            label={t('aiProposalLabel')}
            checked={settings.preferences.ai_proposal}
            onCheckedChange={(v) => { void handleToggle('ai_proposal', v) }}
          />
          <ToggleRow
            label={t('executionCompleteLabel')}
            checked={settings.preferences.execution_complete}
            onCheckedChange={(v) => { void handleToggle('execution_complete', v) }}
          />
        </div>

        {/* リスク・安全 */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t('riskSafetySection')}
          </p>
          {/* HF 警告 — 変更不可 */}
          <ToggleRow
            label={t('healthFactorLabel')}
            checked={settings.preferences.health_factor_warning}
            onCheckedChange={() => {}}
            immutable
            immutableLabel={t('immutableBadge')}
          />
          {/* 緊急停止 — 変更不可 */}
          <ToggleRow
            label={t('emergencyStopLabel')}
            checked={settings.preferences.emergency_stop}
            onCheckedChange={() => {}}
            immutable
            immutableLabel={t('immutableBadge')}
          />
        </div>

        {/* レポート */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t('reportSection')}
          </p>
          <ToggleRow
            label={t('monthlyReportLabel')}
            checked={settings.preferences.monthly_report}
            onCheckedChange={(v) => { void handleToggle('monthly_report', v) }}
          />
          <ToggleRow
            label={t('systemNoticeLabel')}
            checked={settings.preferences.system_notice}
            onCheckedChange={(v) => { void handleToggle('system_notice', v) }}
          />
        </div>

        {/* テスト送信ボタン */}
        <Button
          variant="outline"
          className="w-full gap-2"
          onClick={() => { void handleTestNotification() }}
          disabled={isSending || (!settings.line_enabled && !settings.push_enabled)}
        >
          <AlertCircle className="h-4 w-4" />
          {isSending ? t('testNotificationSending') : t('testNotificationBtn')}
        </Button>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// ToggleRow — 内部ヘルパーコンポーネント
// ---------------------------------------------------------------------------

interface ToggleRowProps {
  label: string
  checked: boolean
  onCheckedChange: (v: boolean) => void
  immutable?: boolean
  immutableLabel?: string
}

function ToggleRow({
  label,
  checked,
  onCheckedChange,
  immutable = false,
  immutableLabel = '',
}: ToggleRowProps) {
  return (
    <div className="flex items-center justify-between rounded-lg border p-3">
      <div className="flex items-center gap-2">
        <p className="text-sm font-medium">{label}</p>
        {immutable && (
          <Badge variant="outline" className="text-xs">
            {immutableLabel}
          </Badge>
        )}
      </div>
      <Switch
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={immutable}
        aria-label={label}
      />
    </div>
  )
}
