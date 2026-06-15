// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/ChatPanel.tsx
// FAB タップで開くチャットパネル — UATa AI
"use client"

import { useState, useRef, useEffect } from "react"
import { useRouter } from "next/navigation"
import { ChevronLeft, History } from "lucide-react"
import { useTranslations } from "next-intl"
import { getAuthToken } from "@/lib/auth/token-key"
import { track, EV } from "@/lib/posthog"

// ---------------------------------------------------------------------------
// 型定義
// ---------------------------------------------------------------------------

interface Message {
  id: string
  role: "user" | "ai"
  content: string
  timestamp: Date
}

interface Props {
  onClose: () => void
}

// ---------------------------------------------------------------------------
// サジェストボタン定義（8 つ）
// ---------------------------------------------------------------------------

type SuggestKey =
  | "suggestStatus"
  | "suggestReason"
  | "suggestHealth"
  | "suggestProfit"
  | "suggestRisk"
  | "suggestMarket"
  | "suggestNext"
  | "suggestRecommend"

type PlaceholderKey =
  | "placeholderStatus"
  | "placeholderReason"
  | "placeholderHealth"
  | "placeholderProfit"
  | "placeholderRisk"
  | "placeholderMarket"
  | "placeholderNext"
  | "placeholderRecommend"

const SUGGEST_CONFIG: Array<{
  id: string
  labelKey: SuggestKey
  promptKey: SuggestKey
  placeholderKey: PlaceholderKey
}> = [
  { id: "status",    labelKey: "suggestStatus",    promptKey: "suggestStatus",    placeholderKey: "placeholderStatus" },
  { id: "reason",    labelKey: "suggestReason",    promptKey: "suggestReason",    placeholderKey: "placeholderReason" },
  { id: "health",    labelKey: "suggestHealth",    promptKey: "suggestHealth",    placeholderKey: "placeholderHealth" },
  { id: "profit",    labelKey: "suggestProfit",    promptKey: "suggestProfit",    placeholderKey: "placeholderProfit" },
  { id: "risk",      labelKey: "suggestRisk",      promptKey: "suggestRisk",      placeholderKey: "placeholderRisk" },
  { id: "market",    labelKey: "suggestMarket",    promptKey: "suggestMarket",    placeholderKey: "placeholderMarket" },
  { id: "next",      labelKey: "suggestNext",      promptKey: "suggestNext",      placeholderKey: "placeholderNext" },
  { id: "recommend", labelKey: "suggestRecommend", promptKey: "suggestRecommend", placeholderKey: "placeholderRecommend" },
]

// ---------------------------------------------------------------------------
// MessageBubble（同ファイル内）
// ---------------------------------------------------------------------------

function MessageBubble({ message }: { message: Message }) {
  const isAI = message.role === "ai"
  return (
    <div className={`flex ${isAI ? "justify-start" : "justify-end"}`}>
      {isAI && (
        <div
          className="w-7 h-7 rounded-full bg-[#1D9E75] flex items-center justify-center
                     text-white text-xs font-bold mr-2 mt-0.5 flex-shrink-0"
        >
          AI
        </div>
      )}
      <div
        className={`max-w-[78%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
          isAI
            ? "ax-card-warm text-[#1c1a27] rounded-tl-none"
            : "bg-[#1D9E75] text-white rounded-tr-none"
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ChatPanel（公開コンポーネント）
// ---------------------------------------------------------------------------

export function ChatPanel({ onClose }: Props) {
  const t = useTranslations("Liff.chat")
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const router = useRouter()

  // 初期挨拶メッセージ（t() が使えるのはクライアントのみ）
  useEffect(() => {
    setMessages([
      {
        id: "init",
        role: "ai",
        content: t("greeting"),
        timestamp: new Date(),
      },
    ])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 新メッセージが追加されるたびに末尾へスクロール
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // 履歴画面へ遷移 (#539 degrade 取りこぼし対策)
  //
  // 旧実装は window.location.href で /liff-history へハード遷移していたため、
  // アプリ全体が再マウントされ useLiff が liffConfigured=true (初期値) から
  // 再 init する。その init 解決前に (liff)/layout.tsx の中央 degrade ガードが
  // 評価され、ブラウザ(非LIFF) や token 復元前のタイミングで
  // 「LINEアプリから開いてください」黒画面・行き止まりが一瞬〜恒久的に出る取りこぼしがあった。
  //
  // ここでは Next.js client router によるソフト遷移に変える。アプリは再マウントされず、
  // 既に解決済みの degrade 状態 (liffConfigured / isLoggedIn) と token がメモリに残るため、
  // liff-chat-history 側は #539 で実装済みの degrade 分岐 (BrowserLoginPrompt / 自動再認証) に
  // 正しく入り、黒画面にならない。LIFF 実機では従来どおり履歴画面へ遷移する。
  const handleHistoryOpen = () => {
    onClose()
    router.push("/liff-chat-history")
  }

  // サジェストボタンタップ → ユーザーメッセージ追加 → AI 返答取得
  const handleSuggest = async (btn: {
    id: string
    label: string
    prompt: string
    placeholderKey: PlaceholderKey
  }) => {
    if (loading) return

    // 行動分析: どのサジェスト（質問カテゴリ）を押したかのみ送る。
    // プライバシー配慮で質問本文は PostHog に送らない（本文は DB chat_messages に保存）。
    track(EV.CHAT_QUESTION, { category: btn.id })

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: btn.label,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    // 0.5 秒ディレイ（タイピングインジケーターを視覚的に見せる）
    await new Promise<void>((resolve) => setTimeout(resolve, 500))

    // token-key 統一: 正準/旧キーの両方を救済する getAuthToken を使う
    // (旧キーで保存済みセッションでも chat API が 401 で取りこぼされないように)。
    const token = getAuthToken() ?? ""
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

    let aiContent: string
    try {
      // バックエンド調査: /api/chat は現時点で未実装のため、
      // 200 以外の場合はプレースホルダーへフォールバックする
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: btn.prompt }),
      })

      if (res.ok) {
        const data = (await res.json()) as {
          response?: string
          message?: string
          content?: string
        }
        aiContent =
          data.response ??
          data.message ??
          data.content ??
          t("responseFallback")
      } else {
        // API 未実装 or エラー → プレースホルダー
        aiContent = t(btn.placeholderKey)
      }
    } catch {
      aiContent = t(btn.placeholderKey)
    }

    const aiMsg: Message = {
      id: `ai-${Date.now()}`,
      role: "ai",
      content: aiContent,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, aiMsg])
    setLoading(false)
  }

  return (
    <>
      {/* バックドロップ */}
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />

      {/* パネル本体 */}
      <div
        className="fixed bottom-0 left-0 right-0 z-50 ax-bg-app
                   h-[88vh] rounded-t-2xl flex flex-col
                   animate-in slide-in-from-bottom duration-300"
      >
        {/* ドラッグハンドル */}
        <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
          <div className="w-8 h-1 rounded-full bg-[#1c1a27]/10" />
        </div>

        {/* ヘッダー */}
        <div className="flex items-center bg-gradient-to-r from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] px-4 py-3 flex-shrink-0">
          <button
            onClick={onClose}
            className="text-[#1c1a27] mr-3 p-0.5 hover:bg-black/5 rounded transition-colors"
            aria-label={t("closeAriaLabel")}
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="text-[#1c1a27] font-semibold text-base leading-none">
              {t("panelTitle")}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className="w-1.5 h-1.5 rounded-full bg-[#1D9E75]" />
              <span className="text-[#2a2440]/70 text-xs">{t("onlineStatus")}</span>
            </div>
          </div>
          <button
            onClick={handleHistoryOpen}
            className="text-[#2a2440]/70 p-1 hover:text-[#1c1a27] hover:bg-black/5 rounded transition-colors"
            aria-label={t("historyAriaLabel")}
          >
            <History className="w-5 h-5" />
          </button>
        </div>

        {/* メッセージエリア */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* タイピングインジケーター */}
          {loading && (
            <div className="flex justify-start">
              <div className="w-7 h-7 rounded-full flex items-center justify-center text-[#2a2440] text-xs font-bold mr-2 mt-0.5 flex-shrink-0" style={{background: 'linear-gradient(135deg, #b9a4f2 0%, #ecaccd 52%, #fbd9a0 100%)'}}>
                AI
              </div>
              <div className="ax-card-warm rounded-2xl rounded-tl-none px-4 py-2.5 max-w-[80%]">
                <div className="flex gap-1 items-center h-4">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="w-1.5 h-1.5 rounded-full bg-[#736f7e] animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* サジェストボタン（固定底部）*/}
        <div className="flex-shrink-0 px-4 pt-3 border-t border-[#1c1a27]/15 ax-safe-bottom">
          <p className="text-[#736f7e] text-xs mb-2">{t("suggestLabel")}</p>
          <div className="grid grid-cols-2 gap-2">
            {SUGGEST_CONFIG.map((cfg) => {
              const label = t(cfg.labelKey)
              const prompt = t(cfg.promptKey)
              return (
                <button
                  key={cfg.id}
                  onClick={() => handleSuggest({ id: cfg.id, label, prompt, placeholderKey: cfg.placeholderKey })}
                  disabled={loading}
                  className="ax-card-warm hover:bg-black/5 active:bg-black/5 disabled:opacity-40
                             text-[#1c1a27] text-xs px-3 py-2.5 rounded-xl text-left transition-colors
                             border border-[#1c1a27]/15 hover:border-[#1c1a27]/15"
                >
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </>
  )
}
