// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-confirm/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { CheckCircle, ChevronDown, ExternalLink } from "lucide-react"
import { getAuthToken } from "@/lib/auth/token-key"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

// 規約 ver03 — id は messages キーとして使用
const ITEM_IDS = ["self_custody", "defi_risk", "user_responsibility", "age_confirm"] as const

export default function LiffConfirmPage() {
  const router = useRouter()
  const t = useTranslations("Liff.confirm")
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const allChecked = ITEM_IDS.every((id) => checked[id])
  const checkedCount = Object.values(checked).filter(Boolean).length

  // terms_agreed_at チェック: 既に同意済みなら /liff-chat へリダイレクト
  useEffect(() => {
    // 正準/旧キー両対応の getAuthToken を使う（liff-confirm だけ直読みで
    // 旧キー保存セッションを取りこぼし、terms-agree が 401 で「押しても無反応」になっていた）。
    const token = getAuthToken()
    if (!token) {
      setLoading(false)
      return
    }

    fetch(`${API_BASE}/api/user/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { terms_agreed_at?: string | null; terms_version?: string | null } | null) => {
        // liff-v3 で同意済みの場合のみスキップ (旧バージョン同意者は再同意を求める)
        if (data?.terms_agreed_at && data?.terms_version === "liff-v3") {
          router.replace("/liff-chat")
        } else {
          setLoading(false)
        }
      })
      .catch(() => setLoading(false))
  }, [router])

  const handleSubmit = async () => {
    if (!allChecked || submitting) return
    setSubmitting(true)
    setError(null)

    const token = getAuthToken()
    // 未認証で叩くと terms-agree が 401 を返し「押しても無反応」になるため、
    // トークンが無ければ黙って失敗させず再ログインへ誘導する。
    if (!token) {
      router.replace("/liff-login")
      return
    }

    try {
      const res = await fetch(`${API_BASE}/api/user/terms-agree`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      })
      if (res.ok) {
        router.replace("/liff-chat")
      } else if (res.status === 401) {
        // セッション切れ — 再ログインへ誘導
        router.replace("/liff-login")
      } else {
        // それ以外の失敗は黙らせず明示（沈黙の失敗を防ぐ）
        setError(t("submitError"))
        setSubmitting(false)
      }
    } catch {
      setError(t("submitError"))
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="w-[375px] mx-auto h-dvh bg-zinc-950 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#1D9E75] border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="w-[375px] mx-auto h-dvh bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden">
      {/* ヘッダー */}
      <div className="bg-[#1a3d2e] px-4 py-5 flex-shrink-0">
        <h1 className="text-white font-bold text-lg">{t("title")}</h1>
        <p className="text-zinc-300 text-sm mt-1">{t("subtitle")}</p>
        {/* ステップドット (ver03: 4 items) */}
        <div className="flex gap-1.5 mt-3">
          {ITEM_IDS.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i < checkedCount ? "bg-[#4ade9a] w-6" : "bg-zinc-700 w-4"
              }`}
            />
          ))}
        </div>
      </div>

      {/* プログレスバー */}
      <div className="px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-center justify-between text-sm mb-1.5">
          <span className="text-zinc-400">{t("progressLabel")}</span>
          <span className="text-[#4ade9a] font-semibold">{checkedCount} / {ITEM_IDS.length}</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#1D9E75] rounded-full transition-all duration-500 ease-out"
            style={{ width: `${(checkedCount / ITEM_IDS.length) * 100}%` }}
          />
        </div>
      </div>

      {/* アコーディオンリスト */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {ITEM_IDS.map((id, idx) => {
          const isChecked = checked[id]
          const isExpanded = expanded[id]
          return (
            <div
              key={id}
              className={`rounded-xl border transition-all duration-200 ${
                isChecked
                  ? "border-[#1D9E75] bg-[#1D9E75]/5"
                  : "border-zinc-800 bg-zinc-900"
              }`}
            >
              <button
                className="flex items-center w-full px-4 py-4 text-left"
                onClick={() =>
                  setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
                }
              >
                <button
                  className="mr-3 flex-shrink-0"
                  onClick={(e) => {
                    e.stopPropagation()
                    setChecked((prev) => ({ ...prev, [id]: !prev[id] }))
                    if (!expanded[id]) {
                      setExpanded((prev) => ({ ...prev, [id]: true }))
                    }
                  }}
                >
                  {isChecked ? (
                    <CheckCircle className="w-6 h-6 text-[#4ade9a]" />
                  ) : (
                    <div className="w-6 h-6 rounded-full border-2 border-zinc-600 flex items-center justify-center">
                      <span className="text-zinc-500 text-xs font-bold">{idx + 1}</span>
                    </div>
                  )}
                </button>
                <span
                  className={`flex-1 text-sm font-medium ${
                    isChecked ? "text-[#4ade9a]" : "text-white"
                  }`}
                >
                  {t(`items.${id}.title`)}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-zinc-500 transition-transform ${
                    isExpanded ? "rotate-180" : ""
                  }`}
                />
              </button>
              {isExpanded && (
                <div className="px-4 pb-4">
                  <p className="text-zinc-400 text-sm leading-relaxed">{t(`items.${id}.detail`)}</p>
                  {!isChecked && (
                    <button
                      onClick={() =>
                        setChecked((prev) => ({ ...prev, [id]: true }))
                      }
                      className="mt-3 w-full py-2.5 rounded-lg bg-[#1D9E75]/20 text-[#4ade9a] text-sm font-medium border border-[#1D9E75]/30 hover:bg-[#1D9E75]/30 transition-colors"
                    >
                      {t("confirmedBtn")}
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 下部: リンク + ボタン */}
      <div className="px-4 pb-8 pt-4 border-t border-zinc-800 flex-shrink-0 space-y-3">
        <div className="flex gap-4 justify-center text-xs text-zinc-500">
          <a
            href="/terms"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-zinc-300"
          >
            {t("termsLink")} <ExternalLink className="w-3 h-3" />
          </a>
          <a
            href="/privacy-policy"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-zinc-300"
          >
            {t("privacyLink")} <ExternalLink className="w-3 h-3" />
          </a>
        </div>
        {error && (
          <p role="alert" className="text-red-400 text-sm text-center">
            {error}
          </p>
        )}
        <button
          disabled={!allChecked || submitting}
          onClick={handleSubmit}
          className={`w-full py-4 rounded-xl font-semibold text-base transition-all duration-200 ${
            allChecked && !submitting
              ? "bg-gradient-to-r from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] text-[#2a2440] hover:brightness-95 active:scale-95"
              : "bg-zinc-800 text-zinc-600 cursor-not-allowed"
          }`}
        >
          {submitting ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              {t("submitting")}
            </span>
          ) : (
            <>
              {t("submitBtn")}
              <span className="block text-[9px] font-normal leading-none mt-1 opacity-75">
                {t("submitBtnSub")}
              </span>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
