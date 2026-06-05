// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { MessageCircle, Bell, AlertTriangle, ShieldAlert, FileText, Info } from "lucide-react"

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

interface NotificationPreferences {
  ai_proposal: boolean
  execution_complete: boolean
  health_factor_warning: boolean
  emergency_stop: boolean
  monthly_report: boolean
  system_notice: boolean
}

interface NotificationSettings {
  line_enabled: boolean
  push_enabled: boolean
  preferences: NotificationPreferences
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

// ---------------------------------------------------------------------------
// Toggle コンポーネント
// ---------------------------------------------------------------------------

function Toggle({
  checked,
  onChange,
  disabled = false,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      aria-checked={checked}
      role="switch"
      className={`relative w-11 h-6 rounded-full transition-colors focus:outline-none ${
        disabled
          ? "opacity-50 cursor-not-allowed bg-zinc-600"
          : checked
          ? "bg-[#1D9E75]"
          : "bg-zinc-700"
      }`}
    >
      <span
        className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  )
}

// ---------------------------------------------------------------------------
// セクションヘッダー
// ---------------------------------------------------------------------------

function SectionHeader({ label }: { label: string }) {
  return (
    <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2 mt-5 first:mt-0">
      {label}
    </p>
  )
}

// ---------------------------------------------------------------------------
// 通知種別行
// ---------------------------------------------------------------------------

function NotificationRow({
  icon,
  label,
  checked,
  onChange,
  disabled = false,
  badge,
}: {
  icon: React.ReactNode
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
  badge?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between bg-zinc-800 rounded-xl px-4 py-3 mb-2">
      <div className="flex items-center gap-3">
        <div className="text-[#4ade9a]">{icon}</div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-white text-sm">{label}</span>
            {badge}
          </div>
        </div>
      </div>
      <Toggle checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// メインコンポーネント
// ---------------------------------------------------------------------------

export function NotificationPanel() {
  const [settings, setSettings] = useState<NotificationSettings>(DEFAULT_SETTINGS)
  const [pushPermission, setPushPermission] = useState<NotificationPermission>("default")
  const [testSending, setTestSending] = useState(false)
  const [testMessage, setTestMessage] = useState<string | null>(null)

  const API_BASE = process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? ""

  function getToken(): string {
    return typeof window !== "undefined" ? (localStorage.getItem("auth_token") ?? "") : ""
  }

  // 権限状態を取得
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setPushPermission(Notification.permission)
    }
  }, [])

  // 設定を取得
  useEffect(() => {
    const token = getToken()
    fetch(`${API_BASE}/api/notifications/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<NotificationSettings>
      })
      .then((data) => setSettings(data))
      .catch(() => {
        // API が存在しない場合はデフォルト状態を保持
      })
  }, [API_BASE])

  // 設定を保存
  async function saveSettings(next: NotificationSettings) {
    setSettings(next)
    const token = getToken()
    try {
      const res = await fetch(`${API_BASE}/api/notifications/settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(next),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch {
      // エラー時は楽観的更新状態を保持
    }
  }

  function updatePref(key: keyof NotificationPreferences, value: boolean) {
    const next: NotificationSettings = {
      ...settings,
      preferences: { ...settings.preferences, [key]: value },
    }
    void saveSettings(next)
  }

  function updateChannel(key: "line_enabled" | "push_enabled", value: boolean) {
    const next: NotificationSettings = { ...settings, [key]: value }
    void saveSettings(next)
  }

  // PWA プッシュ通知 ON→OFF/ON
  async function handlePushToggle(value: boolean) {
    if (value && pushPermission !== "granted") {
      if ("Notification" in window) {
        const result = await Notification.requestPermission()
        setPushPermission(result)
        if (result !== "granted") return
      } else {
        return
      }
    }
    updateChannel("push_enabled", value)
  }

  // テスト通知
  async function handleTestNotification() {
    setTestSending(true)
    setTestMessage(null)
    const token = getToken()
    try {
      const res = await fetch(`${API_BASE}/api/notifications/push/test`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        setTestMessage("テスト通知を送信しました")
      } else {
        setTestMessage("送信に失敗しました（API未実装の可能性があります）")
      }
    } catch {
      setTestMessage("送信に失敗しました")
    } finally {
      setTestSending(false)
      setTimeout(() => setTestMessage(null), 4000)
    }
  }

  const pushBadge =
    pushPermission === "granted" ? (
      <span className="text-[10px] text-[#4ade9a] font-semibold">許可済み</span>
    ) : (
      <span className="text-[10px] text-yellow-400 font-semibold">未許可</span>
    )

  return (
    <div className="pb-4">
      {/* 通知チャネル */}
      <SectionHeader label="通知チャネル" />

      {/* LINE 通知 */}
      <div className="flex items-center justify-between bg-zinc-800 rounded-xl px-4 py-3 mb-2">
        <div className="flex items-center gap-3">
          <MessageCircle className="w-5 h-5 text-[#4ade9a]" />
          <div>
            <div className="text-white text-sm">LINE 通知</div>
            <div className="text-[#4ade9a] text-xs">接続済み</div>
          </div>
        </div>
        <Toggle
          checked={settings.line_enabled}
          onChange={(v) => updateChannel("line_enabled", v)}
        />
      </div>

      {/* PWA プッシュ通知 */}
      <div className="flex items-center justify-between bg-zinc-800 rounded-xl px-4 py-3 mb-2">
        <div className="flex items-center gap-3">
          <Bell className="w-5 h-5 text-[#4ade9a]" />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-white text-sm">PWA プッシュ通知</span>
              {pushBadge}
            </div>
          </div>
        </div>
        <Toggle
          checked={settings.push_enabled}
          onChange={handlePushToggle}
        />
      </div>

      {/* AI・取引 */}
      <SectionHeader label="AI・取引" />

      <NotificationRow
        icon={<Bell className="w-5 h-5" />}
        label="AI 提案通知"
        checked={settings.preferences.ai_proposal}
        onChange={(v) => updatePref("ai_proposal", v)}
      />
      <NotificationRow
        icon={<Bell className="w-5 h-5" />}
        label="実行完了通知"
        checked={settings.preferences.execution_complete}
        onChange={(v) => updatePref("execution_complete", v)}
      />

      {/* リスク・安全 */}
      <SectionHeader label="リスク・安全" />

      <NotificationRow
        icon={<AlertTriangle className="w-5 h-5" />}
        label="Health Factor 警告"
        checked={settings.preferences.health_factor_warning}
        onChange={(v) => updatePref("health_factor_warning", v)}
      />
      <div className="flex items-center justify-between bg-zinc-800 rounded-xl px-4 py-3 mb-2">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 text-[#4ade9a]" />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-white text-sm">緊急停止通知</span>
              <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-700 px-1.5 py-0.5 rounded">
                変更不可
              </span>
            </div>
          </div>
        </div>
        <Toggle
          checked={settings.preferences.emergency_stop}
          onChange={() => {}}
          disabled={true}
        />
      </div>

      {/* レポート */}
      <SectionHeader label="レポート" />

      <NotificationRow
        icon={<FileText className="w-5 h-5" />}
        label="月次レポート"
        checked={settings.preferences.monthly_report}
        onChange={(v) => updatePref("monthly_report", v)}
      />
      <NotificationRow
        icon={<Info className="w-5 h-5" />}
        label="システムお知らせ"
        checked={settings.preferences.system_notice}
        onChange={(v) => updatePref("system_notice", v)}
      />

      {/* テスト通知ボタン */}
      <button
        type="button"
        onClick={handleTestNotification}
        disabled={testSending}
        className="w-full py-3 border border-zinc-700 text-zinc-300 rounded-xl text-sm hover:bg-zinc-800 transition-colors mt-4 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {testSending ? "送信中..." : "テスト通知を送信"}
      </button>

      {testMessage && (
        <p className="text-center text-xs mt-2 text-zinc-400">{testMessage}</p>
      )}
    </div>
  )
}
