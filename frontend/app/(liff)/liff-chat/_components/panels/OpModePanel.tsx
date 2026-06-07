// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { Bot, MousePointer2 } from "lucide-react"
import { getAuthToken } from "@/lib/auth/token-key"

type UserMode = "managed" | "active"

interface ModeOption {
  id: UserMode
  label: string
  desc: string
  icon: React.ElementType
  color: string
  bg: string
  border: string
}

const MODES: ModeOption[] = [
  {
    id: "managed",
    label: "完全おまかせ",
    desc: "AIが自動で判断・実行。承認不要。実行後にLINEで通知。",
    icon: Bot,
    color: "text-[#4ade9a]",
    bg: "bg-[#1D9E75]/10",
    border: "border-[#1D9E75]",
  },
  {
    id: "active",
    label: "アクティブ",
    desc: "AIが提案。自分で承認してから実行。",
    icon: MousePointer2,
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500",
  },
]

const MODE_LABEL: Record<UserMode, string> = {
  managed: "完全おまかせ",
  active: "アクティブ",
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export function OpModePanel() {
  const [currentMode, setCurrentMode] = useState<UserMode | null>(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<string | null>(null)

  // 初回ロード: GET /api/user/settings
  useEffect(() => {
    const token = getAuthToken()
    if (!token) {
      setLoading(false)
      return
    }
    fetch(`${API_BASE}/api/user/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
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
      setToast("認証が切れています。再ログインしてください")
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
      setToast(`「${MODE_LABEL[newMode]}」に切り替えました`)
      setTimeout(() => setToast(null), 2500)
    } catch {
      // ロールバック
      setCurrentMode(prev)
      setToast("切り替えに失敗しました")
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
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-xl bg-zinc-800 border border-zinc-700 text-white text-sm shadow-lg whitespace-nowrap"
        >
          {toast}
        </div>
      )}

      {/* 現在のモード表示カード */}
      <div className="bg-[#1a3d2e] rounded-2xl px-4 py-4 flex items-center justify-between">
        <div>
          <p className="text-xl font-bold text-white" data-testid="opmode-current">
            {loading
              ? "読み込み中..."
              : currentMode
              ? MODE_LABEL[currentMode]
              : "未設定"}
          </p>
          <p className="text-zinc-300 text-sm mt-0.5">現在の運用モード</p>
        </div>
        <span className="text-xs text-[#4ade9a] border border-[#1D9E75] rounded-full px-2 py-1">
          設定中
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
                  <p className="text-white font-bold text-base">{mode.label}</p>
                  <p className="text-zinc-300 text-sm mt-0.5">{mode.desc}</p>
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
