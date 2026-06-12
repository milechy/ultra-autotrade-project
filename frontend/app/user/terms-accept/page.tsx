// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/user/terms-accept/page.tsx
//
// ブラウザ wallet 経路の利用規約同意ページ。
// BrowserTermsGate が未同意ユーザーをここへリダイレクトする。
// 同意送信成功後は /user/dashboard へ遷移する（冪等）。
//
// UI 構成は (liff)/liff-confirm/page.tsx に準拠。

"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { CheckCircle, ChevronDown, ExternalLink } from "lucide-react"
import { getAuthToken } from "@/lib/auth/token-key"
import { acceptTerms, getTermsStatus } from "@/lib/api/auth"

/** ブラウザ経路で記録する同意バージョン（backend _ACCEPTED_TERMS_VERSIONS と一致） */
const BROWSER_TERMS_VERSION = "2.0"

const ITEM_IDS = ["self_custody", "defi_risk", "user_responsibility"] as const
type ItemId = typeof ITEM_IDS[number]
const ITEM_KEY_MAP: Record<ItemId, "item1" | "item2" | "item3"> = {
  self_custody: "item1",
  defi_risk: "item2",
  user_responsibility: "item3",
}

export default function BrowserTermsAcceptPage() {
  const router = useRouter()
  const t = useTranslations("TermsAccept")
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)

  const allChecked = ITEM_IDS.every((id) => checked[id])
  const checkedCount = Object.values(checked).filter(Boolean).length

  // 既同意チェック: 既に同意済みなら /user/dashboard へ即リダイレクト（冪等）
  useEffect(() => {
    const token = getAuthToken()
    if (!token) {
      setLoading(false)
      return
    }

    getTermsStatus(token)
      .then((data) => {
        if (!data.needs_acceptance) {
          router.replace("/user/dashboard")
        } else {
          setLoading(false)
        }
      })
      .catch(() => setLoading(false))
  }, [router])

  const handleSubmit = async () => {
    if (!allChecked || submitting) return
    setSubmitting(true)

    const token = getAuthToken()
    if (!token) {
      setSubmitting(false)
      return
    }

    try {
      await acceptTerms(token, BROWSER_TERMS_VERSION)
      router.replace("/user/dashboard")
    } catch {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#1D9E75] border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="max-w-[480px] mx-auto min-h-screen bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden">
      {/* header */}
      <div className="bg-[#1a3d2e] px-4 py-5 flex-shrink-0">
        <h1 className="text-white font-bold text-lg">{t("title")}</h1>
        <p className="text-zinc-300 text-sm mt-1">{t("subtitle")}</p>
        {/* step dots */}
        <div className="flex gap-1.5 mt-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i < checkedCount ? "bg-[#4ade9a] w-6" : "bg-zinc-700 w-4"
              }`}
            />
          ))}
        </div>
      </div>

      {/* progress bar */}
      <div className="px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-center justify-between text-sm mb-1.5">
          <span className="text-zinc-400">{t("progressLabel")}</span>
          <span className="text-[#4ade9a] font-semibold">{checkedCount} / 3</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#1D9E75] rounded-full transition-all duration-500 ease-out"
            style={{ width: `${(checkedCount / 3) * 100}%` }}
          />
        </div>
      </div>

      {/* accordion list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {ITEM_IDS.map((id, idx) => {
          const msgKey = ITEM_KEY_MAP[id]
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
              {/* interactive content (button) のネスト禁止 (HTML 仕様) のため外側は div + role="button" */}
              <div
                role="button"
                tabIndex={0}
                className="flex items-center w-full px-4 py-4 text-left cursor-pointer"
                onClick={() =>
                  setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
                  }
                }}
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
                  {t(`${msgKey}.title`)}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-zinc-500 transition-transform ${
                    isExpanded ? "rotate-180" : ""
                  }`}
                />
              </div>
              {isExpanded && (
                <div className="px-4 pb-4">
                  <p className="text-zinc-400 text-sm leading-relaxed">{t(`${msgKey}.detail`)}</p>
                  {!isChecked && (
                    <button
                      onClick={() =>
                        setChecked((prev) => ({ ...prev, [id]: true }))
                      }
                      className="mt-3 w-full py-2.5 rounded-lg bg-[#1D9E75]/20 text-[#4ade9a] text-sm font-medium border border-[#1D9E75]/30 hover:bg-[#1D9E75]/30 transition-colors"
                    >
                      {t("confirmItem")}
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* footer: links + button */}
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
        <button
          disabled={!allChecked || submitting}
          onClick={handleSubmit}
          className={`w-full py-4 rounded-xl font-semibold text-base transition-all duration-200 ${
            allChecked && !submitting
              ? "bg-[#1D9E75] text-white hover:bg-[#1D9E75]/90 active:scale-95"
              : "bg-zinc-800 text-zinc-600 cursor-not-allowed"
          }`}
        >
          {submitting ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              {t("saving")}
            </span>
          ) : (
            t("startButton")
          )}
        </button>
      </div>
    </div>
  )
}
