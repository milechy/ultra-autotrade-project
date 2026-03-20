'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

export const dynamic = 'force-dynamic'

import { useState, useEffect, useCallback } from 'react'
import { Bell, TrendingUp, ShieldAlert, Save, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import AuthGuard from '@/components/AuthGuard'
import { EmergencyStop } from '@/components/user/EmergencyStop'
import { useAuth } from '@/lib/auth'
import { UserProviders } from '@/components/user/UserProviders'
import { getJson, putJson } from '@/lib/api/http'

type NotificationLevel = 'all' | 'alert' | 'emergency'

type UserSettings = {
  slack_enabled: boolean
  line_enabled: boolean
  notification_level: NotificationLevel
  shadow_mode: boolean
  exchange_symbol: string
  leverage: number
  max_position_pct: number
  max_daily_trades: number
  hf_threshold: number
}

const DEFAULT_SETTINGS: UserSettings = {
  slack_enabled: false,
  line_enabled: false,
  notification_level: 'alert',
  shadow_mode: true,
  exchange_symbol: 'BTC/USDT',
  leverage: 1,
  max_position_pct: 10,
  max_daily_trades: 30,
  hf_threshold: 1.6,
}

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? 'bg-primary' : 'bg-muted'
      }`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
  return (
    <div className="flex items-center gap-2 pb-1">
      <Icon className="h-4 w-4 text-muted-foreground" />
      <span className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        {title}
      </span>
    </div>
  )
}

function SettingsPage() {
  const { token } = useAuth()
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [isStopped, setIsStopped] = useState(false)

  const fetchSettings = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      const data = await getJson<UserSettings & { is_trading_paused?: boolean }>(
        '/users/settings',
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setSettings({ ...DEFAULT_SETTINGS, ...data })
      if (data.is_trading_paused != null) setIsStopped(data.is_trading_paused)
    } catch {
      // use defaults silently if endpoint not ready
    } finally {
      setIsLoading(false)
    }
  }, [token])

  useEffect(() => {
    fetchSettings()
  }, [fetchSettings])

  const handleSave = async () => {
    if (!token) return
    setIsSaving(true)
    setError(null)
    try {
      await putJson('/users/settings', settings, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setSuccessMsg('設定を保存しました')
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '保存エラー'
      setError(`保存失敗: ${msg}`)
    } finally {
      setIsSaving(false)
    }
  }

  const set = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const notificationLevelOptions: { value: NotificationLevel; label: string }[] = [
    { value: 'all', label: '全て' },
    { value: 'alert', label: 'ALERT以上' },
    { value: 'emergency', label: 'EMERGENCYのみ' },
  ]

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen text-muted-foreground">
        <RefreshCw className="mb-3 h-8 w-8 animate-spin" />
        <p className="text-sm">読み込み中...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="flex items-center justify-between px-4 py-3">
          <h1 className="text-lg font-semibold">設定</h1>
          <Button size="sm" onClick={handleSave} disabled={isSaving}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {isSaving ? '保存中...' : '保存'}
          </Button>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4 pb-8">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {successMsg && (
          <Alert>
            <AlertDescription>{successMsg}</AlertDescription>
          </Alert>
        )}

        {/* 通知設定 */}
        <Card>
          <CardHeader className="pb-3">
            <SectionHeader icon={Bell} title="通知設定" />
            <CardTitle className="text-base">通知</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Slack通知</p>
                <p className="text-xs text-muted-foreground">取引・アラートをSlackに送信</p>
              </div>
              <Toggle
                checked={settings.slack_enabled}
                onChange={v => set('slack_enabled', v)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">LINE通知</p>
                <p className="text-xs text-muted-foreground">取引・アラートをLINEに送信</p>
              </div>
              <Toggle
                checked={settings.line_enabled}
                onChange={v => set('line_enabled', v)}
              />
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">通知レベル</p>
              <div className="flex gap-2 flex-wrap">
                {notificationLevelOptions.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => set('notification_level', opt.value)}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      settings.notification_level === opt.value
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground hover:bg-muted/80'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 取引設定 */}
        <Card>
          <CardHeader className="pb-3">
            <SectionHeader icon={TrendingUp} title="取引設定" />
            <CardTitle className="text-base">取引</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Shadow Mode</p>
                <p className="text-xs text-muted-foreground">ONにすると実際の注文は発生しません</p>
              </div>
              <Toggle
                checked={settings.shadow_mode}
                onChange={v => set('shadow_mode', v)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">取引ペア</label>
              <Input
                value={settings.exchange_symbol}
                onChange={e => set('exchange_symbol', e.target.value)}
                placeholder="例: BTC/USDT"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">レバレッジ</label>
              <Input
                type="number"
                min={1}
                max={20}
                value={settings.leverage}
                onChange={e => set('leverage', Number(e.target.value))}
              />
            </div>

            {/* Bot売買設定 */}
            <div className="flex items-center justify-between p-4 border rounded-lg opacity-60">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">Bot売買</span>
                  <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">Coming Soon</span>
                </div>
                <p className="text-sm text-muted-foreground mt-1">Phase 2で対応予定</p>
              </div>
              <input type="checkbox" disabled checked={false} className="w-5 h-5 cursor-not-allowed" />
            </div>
          </CardContent>
        </Card>

        {/* リスク管理 */}
        <Card>
          <CardHeader className="pb-3">
            <SectionHeader icon={ShieldAlert} title="リスク管理" />
            <CardTitle className="text-base">リスク</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">最大ポジション (%)</label>
              <p className="text-xs text-muted-foreground">総資産に対する1回あたりの最大取引割合</p>
              <Input
                type="number"
                min={1}
                max={100}
                step={1}
                value={settings.max_position_pct}
                onChange={e => set('max_position_pct', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">1日の最大取引数</label>
              <Input
                type="number"
                min={1}
                max={100}
                value={settings.max_daily_trades}
                onChange={e => set('max_daily_trades', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Health Factor 下限</label>
              <p className="text-xs text-muted-foreground">この値を下回ると自動的に取引を停止します</p>
              <Input
                type="number"
                min={1.0}
                max={3.0}
                step={0.1}
                value={settings.hf_threshold}
                onChange={e => set('hf_threshold', Number(e.target.value))}
              />
            </div>
          </CardContent>
        </Card>

        {/* 緊急停止 */}
        <EmergencyStop
          isStopped={isStopped}
          onStopped={() => setIsStopped(true)}
        />

        <Button className="w-full" onClick={handleSave} disabled={isSaving}>
          <Save className="mr-2 h-4 w-4" />
          {isSaving ? '保存中...' : '設定を保存'}
        </Button>
      </div>
    </div>
  )
}

export default function UserSettingsPage() {
  return (
    <UserProviders>
      <AuthGuard>
        <SettingsPage />
      </AuthGuard>
    </UserProviders>
  )
}