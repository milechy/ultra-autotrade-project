// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { usePrivy } from "@privy-io/react-auth"
import { Copy, LogOut, Trash2, Building2, ChevronDown, Check } from "lucide-react"

interface UserData {
  id?: number
  email?: string
  username?: string
  user_mode?: "managed" | "active" | "pro"
  created_at?: string
  wallet_address?: string
  // corporate fields (frontend-only state — not yet in backend schema)
}

interface CorpForm {
  name: string
  number: string
  rep: string
  month: number
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export function AccountPanel() {
  const router = useRouter()
  const { logout: privyLogout } = usePrivy()
  const [userData, setUserData] = useState<UserData | null>(null)
  const [corpExpanded, setCorpExpanded] = useState(false)
  const [corpForm, setCorpForm] = useState<CorpForm>({ name: "", number: "", rep: "", month: 0 })
  const [corpSaved, setCorpSaved] = useState(false)
  const [deleteSheet, setDeleteSheet] = useState(false)
  const [toastMsg, setToastMsg] = useState("")
  const [copied, setCopied] = useState(false)

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setTimeout(() => setToastMsg(""), 2000)
  }

  // ユーザー設定を取得（/api/user/settings + /auth/me を併用）
  useEffect(() => {
    const token =
      typeof window !== "undefined" ? (localStorage.getItem("auth_token") ?? "") : ""
    if (!token) return

    // settings エンドポイント（user_mode 等）
    fetch(`${API_BASE}/api/user/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: UserData | null) => {
        if (data) setUserData((prev) => ({ ...prev, ...data }))
      })
      .catch(() => {})

    // auth/me エンドポイント（created_at, wallet_address）
    fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then(
        (
          data: {
            email?: string
            created_at?: string
            wallet_address?: string
          } | null,
        ) => {
          if (data) {
            setUserData((prev) => ({
              ...prev,
              ...(data.email && { email: data.email }),
              ...(data.created_at && { created_at: data.created_at }),
              ...(data.wallet_address && { wallet_address: data.wallet_address }),
            }))
          }
        },
      )
      .catch(() => {})
  }, [])

  // 法人情報を localStorage から復元
  useEffect(() => {
    try {
      const saved = localStorage.getItem("liff_corp_info")
      if (saved) {
        const parsed = JSON.parse(saved) as CorpForm
        setCorpForm(parsed)
      }
    } catch {
      // ignore
    }
  }, [])

  // イニシャル生成
  const getInitial = () => {
    if (userData?.username) return userData.username.charAt(0).toUpperCase()
    if (userData?.email) return userData.email.charAt(0).toUpperCase()
    return "U"
  }

  // 表示名（username か email の @ 前）
  const getDisplayName = () => {
    if (userData?.username) return userData.username
    if (userData?.email) return userData.email.split("@")[0]
    return "ユーザー"
  }

  // ウォレットアドレス短縮表示
  const getShortAddress = () => {
    const addr = userData?.wallet_address
    if (!addr) return null
    return `${addr.slice(0, 6)}…${addr.slice(-4)}`
  }

  // 運用開始日フォーマット
  const getStartedAt = () => {
    if (!userData?.created_at) return "—"
    const d = new Date(userData.created_at)
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
  }

  // 運用モード表示
  const getModeLabel = () => {
    if (userData?.user_mode === "managed") return "完全おまかせ"
    if (userData?.user_mode === "active") return "アクティブ"
    return "—"
  }

  // ウォレットアドレスコピー
  const handleCopyWallet = async () => {
    const addr = userData?.wallet_address
    if (!addr) return
    try {
      await navigator.clipboard.writeText(addr)
      setCopied(true)
      showToast("コピーしました")
      setTimeout(() => setCopied(false), 2000)
    } catch {
      showToast("コピーできませんでした")
    }
  }

  // 法人情報保存（フロントエンドのみ保持 — backend 未実装のためローカル保存）
  const handleCorpSave = () => {
    // 将来バックエンドが corporate_* フィールドを実装した時点で PUT /api/user/settings に送る
    // 現時点は localStorage に保存してフロント内で表示するのみ
    try {
      localStorage.setItem("liff_corp_info", JSON.stringify(corpForm))
    } catch {
      // ignore
    }
    setCorpSaved(true)
    showToast("保存しました")
    setTimeout(() => setCorpSaved(false), 2000)
  }

  // ログアウト
  const handleLogout = async () => {
    const { getLiff, isLiffConfigured } = await import("@/lib/liff/init")
    const liffMode = isLiffConfigured()

    // 1. Privy ログアウト
    try {
      await privyLogout()
    } catch {
      // ignore
    }

    // 2. LINE LIFF ログアウト（LIFF モードのみ。ブラウザ PWA モードでは skip）
    if (liffMode) {
      try {
        const liff = await getLiff()
        if (liff.isLoggedIn()) liff.logout()
      } catch {
        // ignore
      }
    }

    // 3. トークンクリア
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token")
    }

    // 4. リダイレクト（LIFF モードは /liff-login、ブラウザは /login）
    router.replace(liffMode ? "/liff-login" : "/login")
  }

  // アカウント削除申請
  const handleDeleteRequest = async () => {
    const token =
      typeof window !== "undefined" ? (localStorage.getItem("auth_token") ?? "") : ""

    try {
      const res = await fetch(`${API_BASE}/api/user/delete-request`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      })
      if (res.ok) {
        showToast("削除申請を受け付けました")
        setDeleteSheet(false)
      } else if (res.status === 404 || res.status === 405) {
        showToast("サポートへお問い合わせください")
        setDeleteSheet(false)
      } else {
        showToast("エラーが発生しました")
      }
    } catch {
      showToast("サポートへお問い合わせください")
      setDeleteSheet(false)
    }
  }

  const shortAddress = getShortAddress()

  return (
    <div className="space-y-4">
      {/* プロフィールカード */}
      <div className="bg-[#1a3d2e] rounded-2xl p-4">
        <div className="flex items-center gap-3">
          {/* イニシャルアバター */}
          <div className="w-14 h-14 rounded-full bg-[#1D9E75]/20 border border-[#1D9E75] flex items-center justify-center text-[#4ade9a] text-xl font-bold flex-shrink-0">
            {getInitial()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white font-semibold truncate">{getDisplayName()}</p>
            {userData?.email && (
              <p className="text-zinc-300 text-sm truncate">{userData.email}</p>
            )}
            {/* ログイン方法バッジ（LIFF = LINE ログイン） */}
            <div className="flex flex-wrap gap-1 mt-1">
              <span className="bg-zinc-800 text-zinc-300 text-xs px-2 py-0.5 rounded-full">
                LINE
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 運用情報セクション */}
      <div className="bg-zinc-900 rounded-xl overflow-hidden">
        {/* 運用開始日 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <span className="text-zinc-400 text-sm">運用開始日</span>
          <span className="text-white text-sm">{getStartedAt()}</span>
        </div>

        {/* 運用モード */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <span className="text-zinc-400 text-sm">運用モード</span>
          <span className="text-white text-sm">{getModeLabel()}</span>
        </div>

        {/* ウォレットアドレス */}
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-zinc-400 text-sm">ウォレット</span>
          {shortAddress ? (
            <button
              onClick={handleCopyWallet}
              className="flex items-center gap-1.5 text-zinc-300 text-sm"
            >
              <span className="font-mono text-xs">{shortAddress}</span>
              {copied ? (
                <Check className="w-3.5 h-3.5 text-[#4ade9a]" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-zinc-500" />
              )}
            </button>
          ) : (
            <span className="text-zinc-600 text-sm">未連携</span>
          )}
        </div>
      </div>

      {/* 法人情報セクション（アコーディオン） */}
      <div className="bg-zinc-900 rounded-xl overflow-hidden">
        <button
          onClick={() => setCorpExpanded((v) => !v)}
          className="flex items-center justify-between w-full px-4 py-3.5"
        >
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-zinc-400" />
            <span className="text-zinc-300 text-sm font-medium">法人として使う</span>
          </div>
          <ChevronDown
            className={`w-4 h-4 text-zinc-500 transition-transform duration-200 ${
              corpExpanded ? "rotate-180" : ""
            }`}
          />
        </button>

        {corpExpanded && (
          <div className="px-4 pb-4 space-y-3 border-t border-zinc-800 pt-3">
            <input
              placeholder="法人名"
              value={corpForm.name}
              onChange={(e) => setCorpForm((p) => ({ ...p, name: e.target.value }))}
              className="w-full bg-zinc-800 text-white px-3 py-2.5 rounded-lg text-sm placeholder-zinc-500 outline-none focus:ring-1 focus:ring-[#1D9E75]"
            />
            <input
              placeholder="法人番号（13桁）"
              value={corpForm.number}
              onChange={(e) => setCorpForm((p) => ({ ...p, number: e.target.value }))}
              maxLength={13}
              inputMode="numeric"
              className="w-full bg-zinc-800 text-white px-3 py-2.5 rounded-lg text-sm placeholder-zinc-500 outline-none focus:ring-1 focus:ring-[#1D9E75]"
            />
            <input
              placeholder="代表者名"
              value={corpForm.rep}
              onChange={(e) => setCorpForm((p) => ({ ...p, rep: e.target.value }))}
              className="w-full bg-zinc-800 text-white px-3 py-2.5 rounded-lg text-sm placeholder-zinc-500 outline-none focus:ring-1 focus:ring-[#1D9E75]"
            />

            {/* 決算月グリッド */}
            <div>
              <p className="text-zinc-400 text-xs mb-2">決算月</p>
              <div className="grid grid-cols-6 gap-1.5">
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <button
                    key={m}
                    onClick={() => setCorpForm((p) => ({ ...p, month: m }))}
                    className={`py-2 rounded-lg text-sm font-medium transition-colors ${
                      corpForm.month === m
                        ? "bg-[#1D9E75] text-white"
                        : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                    }`}
                  >
                    {m}月
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={handleCorpSave}
              disabled={!corpForm.name || !corpForm.number || !corpForm.rep || !corpForm.month}
              className="w-full py-3 bg-[#1D9E75] text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            >
              {corpSaved ? "保存しました ✓" : "保存する"}
            </button>
          </div>
        )}
      </div>

      {/* ログアウトボタン */}
      <button
        onClick={handleLogout}
        className="flex items-center gap-3 w-full px-4 py-4 bg-zinc-900 rounded-xl hover:bg-zinc-800 transition-colors"
      >
        <LogOut className="w-5 h-5 text-red-400" />
        <span className="text-red-400 font-medium">ログアウト</span>
      </button>

      {/* アカウント削除ボタン */}
      <div className="flex justify-center pb-2">
        <button
          onClick={() => setDeleteSheet(true)}
          className="flex items-center gap-2 px-4 py-2 text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
          <span className="text-xs">アカウントを削除</span>
        </button>
      </div>

      {/* 削除確認ボトムシート */}
      {deleteSheet && (
        <>
          <div
            className="fixed inset-0 z-[60] bg-black/60"
            onClick={() => setDeleteSheet(false)}
          />
          <div
            className="fixed bottom-0 left-0 right-0 z-[70] bg-zinc-900 rounded-t-2xl px-4 pb-8 pt-4
                        animate-in slide-in-from-bottom duration-300"
          >
            <div className="mx-auto mb-4 h-1 w-8 rounded-full bg-zinc-700" />
            <h3 className="text-white font-semibold mb-2">アカウントを削除しますか？</h3>
            <p className="text-zinc-400 text-sm mb-6">
              残高がある場合、削除申請を受け付けられません。先に全額出金してください。
            </p>
            <button
              onClick={handleDeleteRequest}
              className="w-full py-3.5 bg-red-600/20 border border-red-600 text-red-400 rounded-xl font-medium mb-3"
            >
              削除を申請する
            </button>
            <button
              onClick={() => setDeleteSheet(false)}
              className="w-full py-3.5 border border-zinc-700 text-zinc-400 rounded-xl font-medium"
            >
              キャンセル
            </button>
          </div>
        </>
      )}

      {/* トースト */}
      {toastMsg && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[80] bg-zinc-700 text-white px-4 py-2 rounded-full text-sm whitespace-nowrap">
          {toastMsg}
        </div>
      )}
    </div>
  )
}
