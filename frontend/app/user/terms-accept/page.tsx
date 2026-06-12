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
import { CheckCircle, ChevronDown, ExternalLink } from "lucide-react"
import { getAuthToken } from "@/lib/auth/token-key"
import { acceptTerms, getTermsStatus } from "@/lib/api/auth"

/** ブラウザ経路で記録する同意バージョン（backend _ACCEPTED_TERMS_VERSIONS と一致） */
const BROWSER_TERMS_VERSION = "2.0"

const ITEMS = [
  {
    id: "self_custody",
    title: "資産はユーザー自身が管理します",
    detail:
      "本サービスはノンカストディアル型です。秘密鍵はユーザーが管理し、弊社はウォレットにアクセスできません。",
  },
  {
    id: "defi_risk",
    title: "DeFi運用にはリスクがあります",
    detail:
      "スマートコントラクトのリスク、価格変動リスク、流動性リスクが存在します。投資は自己責任でお願いします。",
  },
  {
    id: "user_responsibility",
    title: "アカウント管理は利用者自身の責任です",
    detail:
      "ログイン情報の管理、不正アクセスへの対応はユーザーご自身の責任となります。弊社はアカウント損失に対して責任を負いません。",
  },
]

export default function BrowserTermsAcceptPage() {
  const router = useRouter()
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)

  const allChecked = ITEMS.every((item) => checked[item.id])
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
      {/* ヘッダー */}
      <div className="bg-[#1a3d2e] px-4 py-5 flex-shrink-0">
        <h1 className="text-white font-bold text-lg">重要事項の確認</h1>
        <p className="text-zinc-300 text-sm mt-1">運用開始前に以下をご確認ください</p>
        {/* ステップドット */}
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

      {/* プログレスバー */}
      <div className="px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-center justify-between text-sm mb-1.5">
          <span className="text-zinc-400">確認状況</span>
          <span className="text-[#4ade9a] font-semibold">{checkedCount} / 3</span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#1D9E75] rounded-full transition-all duration-500 ease-out"
            style={{ width: `${(checkedCount / 3) * 100}%` }}
          />
        </div>
      </div>

      {/* アコーディオンリスト */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {ITEMS.map((item, idx) => {
          const isChecked = checked[item.id]
          const isExpanded = expanded[item.id]
          return (
            <div
              key={item.id}
              className={`rounded-xl border transition-all duration-200 ${
                isChecked
                  ? "border-[#1D9E75] bg-[#1D9E75]/5"
                  : "border-zinc-800 bg-zinc-900"
              }`}
            >
              <button
                className="flex items-center w-full px-4 py-4 text-left"
                onClick={() =>
                  setExpanded((prev) => ({ ...prev, [item.id]: !prev[item.id] }))
                }
              >
                <button
                  className="mr-3 flex-shrink-0"
                  onClick={(e) => {
                    e.stopPropagation()
                    setChecked((prev) => ({ ...prev, [item.id]: !prev[item.id] }))
                    if (!expanded[item.id]) {
                      setExpanded((prev) => ({ ...prev, [item.id]: true }))
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
                  {item.title}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-zinc-500 transition-transform ${
                    isExpanded ? "rotate-180" : ""
                  }`}
                />
              </button>
              {isExpanded && (
                <div className="px-4 pb-4">
                  <p className="text-zinc-400 text-sm leading-relaxed">{item.detail}</p>
                  {!isChecked && (
                    <button
                      onClick={() =>
                        setChecked((prev) => ({ ...prev, [item.id]: true }))
                      }
                      className="mt-3 w-full py-2.5 rounded-lg bg-[#1D9E75]/20 text-[#4ade9a] text-sm font-medium border border-[#1D9E75]/30 hover:bg-[#1D9E75]/30 transition-colors"
                    >
                      確認しました
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
            利用規約 <ExternalLink className="w-3 h-3" />
          </a>
          <a
            href="/privacy-policy"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-zinc-300"
          >
            プライバシーポリシー <ExternalLink className="w-3 h-3" />
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
              保存中...
            </span>
          ) : (
            "運用を開始する"
          )}
        </button>
      </div>
    </div>
  )
}
