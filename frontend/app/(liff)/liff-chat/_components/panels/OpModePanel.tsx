// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { Bot, MousePointer2 } from "lucide-react"
import { useTranslations } from "next-intl"
import { getAuthToken } from "@/lib/auth/token-key"
import { liffFetch } from "@/lib/liff/liff-fetch"
import { track, EV } from "@/lib/posthog"

type UserMode = "managed" | "active"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export function OpModePanel() {
  const t = useTranslations("Liff.panels.opMode")
  const [currentMode, setCurrentMode] = useState<UserMode | null>(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<string | null>(null)

  const MODES = [
    {
      id: "managed" as UserMode,
      label: t("managedLabel"),
      desc: t("managedDesc"),
      icon: Bot,
      color: "text-[#1D9E75]",
      bg: "bg-[#1D9E75]/10",
      border: "border-[#1D9E75]",
    },
    {
      id: "active" as UserMode,
      label: t("activeLabel"),
      desc: t("activeDesc"),
      icon: MousePointer2,
      color: "text-blue-600",
      bg: "bg-blue-500/10",
      border: "border-blue-500",
    },
  ]

  const MODE_LABEL: Record<UserMode, string> = {
    managed: t("managedLabel"),
    active: t("activeLabel"),
  }

  // 初回ロード: GET /api/user/settings
  useEffect(() => {
    liffFetch("/api/user/settings")
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: { user_mode: UserMode }) => {
        setCurrentMode(data.user_mode)
      })
      .catch(() => {
        // 取得失敗時はデフォルト表示なし
      })
      .finally(() => setLoading(false))
  }, [])

  // モード切替（確認ステップ無しで即切替）
  async function handleSelect(newMode: UserMode) {
    if (newMode === currentMode) return
    const token = getAuthToken()
    if (!token) {
      setToast(t("toastAuthExpired"))
      setTimeout(() => setToast(null), 2500)
      return
    }
    // 楽観的更新
    const prev = currentMode
    setCurrentMode(newMode)
    try {
      const res = await fetch(`${API_BASE}/api/user/settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ user_mode: newMode }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      track(EV.OPMODE_CHANGE, { mode: newMode })
      setToast(t("toastSwitched", { mode: MODE_LABEL[newMode] }))
      setTimeout(() => setToast(null), 2500)
    } catch {
      // ロールバック
      setCurrentMode(prev)
      setToast(t("toastSwitchFailed"))
      setTimeout(() => setToast(null), 2500)
    }
  }

  return (
    <div className="space-y-4 relative" data-testid="opmode-panel">
      {/* トースト */}
      {toast && (
        <div
          role="status"
          data-testid="opmode-toast"
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-xl bg-[#1b1a23] border border-[#1c1a27]/15 text-[#fbf7f0] text-sm shadow-lg whitespace-nowrap"
        >
          {toast}
        </div>
      )}

      {/* 現在のモード表示カード */}
      <div className="bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] rounded-2xl px-4 py-4 flex items-center justify-between">
        <div>
          <p className="text-xl font-bold text-[#1c1a27]" data-testid="opmode-current">
            {loading
              ? t("loadingMode")
              : currentMode
              ? MODE_LABEL[currentMode]
              : t("modeUnset")}
          </p>
          <p className="text-[#736f7e] text-sm mt-0.5">{t("currentModeLabel")}</p>
        </div>
        <span className="text-xs text-[#1D9E75] border border-[#1D9E75] rounded-full px-2 py-1">
          {t("activeBadge")}
        </span>
      </div>

      {/* モード選択カード */}
      <div className="space-y-3">
        {MODES.map((mode) => {
          const Icon = mode.icon
          const isSelected = currentMode === mode.id
          return (
            <button
              key={mode.id}
              type="button"
              data-testid={`opmode-option-${mode.id}`}
              aria-pressed={isSelected}
              onClick={() => handleSelect(mode.id)}
              className={[
                "w-full text-left rounded-2xl border-2 p-4 transition-all",
                mode.bg,
                mode.border,
                isSelected ? "opacity-100" : "opacity-60",
              ].join(" ")}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-6 h-6 shrink-0 ${mode.color}`} />
                <div>
                  <p className="text-[#1c1a27] font-bold text-base">{mode.label}</p>
                  <p className="text-[#736f7e] text-sm mt-0.5">{mode.desc}</p>
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
