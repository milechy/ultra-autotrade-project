// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { MessageCircle, Bell, AlertTriangle, ShieldAlert, FileText, Info } from "lucide-react"
import { useTranslations } from "next-intl"
import { getAuthToken } from "@/lib/auth/token-key"
import { liffFetch } from "@/lib/liff/liff-fetch"
import { isLiffConfigured } from "@/lib/liff/init"

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
  // track 色: ON は緑(#1D9E75)、OFF はグレー。disabled は opacity で薄める
  // (track 自体の色は checked 状態を維持して「ON 固定」が一目で判る見た目にする)。
  const trackColor = checked ? "bg-[#1D9E75]" : "bg-[#1c1a27]/15"
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      aria-checked={checked}
      role="switch"
      className={`relative inline-flex flex-shrink-0 w-11 h-6 rounded-full transition-colors focus:outline-none ${trackColor} ${
        disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
      }`}
    >
      {/* ノブ: absolute だが left を明示しないと static 位置(右端)から
          translate されて中間に潰れる。left-0.5 で左端基準に固定し、
          ON は translate-x-5 で右へ、OFF は translate-x-0 で左端。 */}
      <span
        className={`pointer-events-none absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
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
    <p className="text-xs font-semibold text-[#736f7e] uppercase tracking-wider mb-2 mt-5 first:mt-0">
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
    <div className="flex items-center justify-between ax-card-warm rounded-xl px-4 py-3 mb-2">
      <div className="flex items-center gap-3">
        <div className="text-[#1D9E75]">{icon}</div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[#1c1a27] text-sm">{label}</span>
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
  const t = useTranslations("Liff.panels.notification")
  const [settings, setSettings] = useState<NotificationSettings>(DEFAULT_SETTINGS)
  const [pushPermission, setPushPermission] = useState<NotificationPermission>("default")
  const [testSending, setTestSending] = useState(false)
  const [testMessage, setTestMessage] = useState<string | null>(null)

  const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

  // token-key.ts の正準キー統一シム経由で取得 (通知設定 401 の連鎖防止)。
  // getAuthToken は AUTH_TOKEN_KEY 優先 + 旧キーフォールバック。SSR/不可時は null → "" に丸める。
  function getToken(): string {
    return getAuthToken() ?? ""
  }

  // 権限状態を取得
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setPushPermission(Notification.permission)
    }
  }, [])

  // 設定を取得
  useEffect(() => {
    liffFetch("/api/notifications/settings")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<NotificationSettings>
      })
      .then((data) => setSettings(data))
      .catch(() => {
        // API が存在しない場合はデフォルト状態を保持
      })
  }, [])

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
        setTestMessage(t("testNotificationSent"))
      } else {
        setTestMessage(t("testNotificationFailed"))
      }
    } catch {
      setTestMessage(t("testNotificationError"))
    } finally {
      setTestSending(false)
      setTimeout(() => setTestMessage(null), 4000)
    }
  }

  const pushBadge =
    pushPermission === "granted" ? (
      <span className="text-[10px] text-[#1D9E75] font-semibold">{t("pushGranted")}</span>
    ) : (
      <span className="text-[10px] text-yellow-600 font-semibold">{t("pushNotGranted")}</span>
    )

  return (
    <div className="pb-4">
      {/* 通知チャネル */}
      <SectionHeader label={t("channelSection")} />

      {/* LINE 通知。LIFF モード（LINE 連携）でのみ表示する。PWA 本番形態
          （NEXT_PUBLIC_LIFF_ID 未設定）では LINE 未接続のため「接続済み」の
          誤表示を避けて行ごと非表示にする。 */}
      {isLiffConfigured() && (
        <div className="flex items-center justify-between ax-card-warm rounded-xl px-4 py-3 mb-2">
          <div className="flex items-center gap-3">
            <MessageCircle className="w-5 h-5 text-[#1D9E75]" />
            <div>
              <div className="text-[#1c1a27] text-sm">{t("lineNotification")}</div>
              <div className="text-[#1D9E75] text-xs">{t("lineConnected")}</div>
            </div>
          </div>
          <Toggle
            checked={settings.line_enabled}
            onChange={(v) => updateChannel("line_enabled", v)}
          />
        </div>
      )}

      {/* PWA プッシュ通知 */}
      <div className="flex items-center justify-between ax-card-warm rounded-xl px-4 py-3 mb-2">
        <div className="flex items-center gap-3">
          <Bell className="w-5 h-5 text-[#1D9E75]" />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[#1c1a27] text-sm">{t("pushNotification")}</span>
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
      <SectionHeader label={t("aiTradeSection")} />

      <NotificationRow
        icon={<Bell className="w-5 h-5" />}
        label={t("aiProposalLabel")}
        checked={settings.preferences.ai_proposal}
        onChange={(v) => updatePref("ai_proposal", v)}
      />
      <NotificationRow
        icon={<Bell className="w-5 h-5" />}
        label={t("executionCompleteLabel")}
        checked={settings.preferences.execution_complete}
        onChange={(v) => updatePref("execution_complete", v)}
      />

      {/* リスク・安全 */}
      <SectionHeader label={t("riskSafetySection")} />

      <NotificationRow
        icon={<AlertTriangle className="w-5 h-5" />}
        label={t("healthFactorLabel")}
        checked={settings.preferences.health_factor_warning}
        onChange={(v) => updatePref("health_factor_warning", v)}
      />
      <div className="flex items-center justify-between ax-card-warm rounded-xl px-4 py-3 mb-2">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 text-[#1D9E75]" />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[#1c1a27] text-sm">{t("emergencyStopLabel")}</span>
              <span className="text-[10px] text-[#fbf7f0] font-semibold bg-[#1b1a23] px-1.5 py-0.5 rounded">
                {t("immutableBadge")}
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
      <SectionHeader label={t("reportSection")} />

      <NotificationRow
        icon={<FileText className="w-5 h-5" />}
        label={t("monthlyReportLabel")}
        checked={settings.preferences.monthly_report}
        onChange={(v) => updatePref("monthly_report", v)}
      />
      <NotificationRow
        icon={<Info className="w-5 h-5" />}
        label={t("systemNoticeLabel")}
        checked={settings.preferences.system_notice}
        onChange={(v) => updatePref("system_notice", v)}
      />

      {/* テスト通知ボタン */}
      <button
        type="button"
        onClick={handleTestNotification}
        disabled={testSending}
        className="w-full py-3 border border-[#1c1a27]/15 text-[#1c1a27] rounded-xl text-sm hover:bg-black/5 transition-colors mt-4 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {testSending ? t("testNotificationSending") : t("testNotificationBtn")}
      </button>

      {testMessage && (
        <p className="text-center text-xs mt-2 text-[#736f7e]">{testMessage}</p>
      )}
    </div>
  )
}
