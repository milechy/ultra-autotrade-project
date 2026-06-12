// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/ChatPanel.tsx
// FAB タップで開くチャットパネル — UATa AI
"use client"

import { useState, useRef, useEffect } from "react"
import { useRouter } from "next/navigation"
import { ChevronLeft, History } from "lucide-react"
import { getAuthToken } from "@/lib/auth/token-key"

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

const SUGGEST_BUTTONS = [
  { id: "status",    label: "今の運用状況は？",    prompt: "現在の運用状況を教えてください" },
  { id: "reason",    label: "今日の判断理由",       prompt: "今日のAI判断の理由を教えてください" },
  { id: "health",    label: "ヘルスファクターは？", prompt: "現在のHealth Factorを教えてください" },
  { id: "profit",    label: "今月の利益",           prompt: "今月の利益を教えてください" },
  { id: "risk",      label: "リスク状況",           prompt: "現在のリスク状況を教えてください" },
  { id: "market",    label: "市場の状況",           prompt: "現在の市場状況を教えてください" },
  { id: "next",      label: "次の動きは？",         prompt: "次の運用の動きについて教えてください" },
  { id: "recommend", label: "アドバイスをください", prompt: "今の私の運用についてアドバイスをください" },
] as const

type SuggestId = typeof SUGGEST_BUTTONS[number]["id"]

// ---------------------------------------------------------------------------
// プレースホルダー応答（/api/chat が未実装の場合のフォールバック）
// ---------------------------------------------------------------------------

function getPlaceholderResponse(id: SuggestId | string): string {
  const responses: Record<string, string> = {
    status:    "現在の運用状況を確認中です。データの取得にしばらくお待ちください。",
    reason:    "今日のAI判断は市場の状況と過去のデータを分析した結果です。詳細はダッシュボードをご確認ください。",
    health:    "Health Factorは安全な範囲内で維持されています。",
    profit:    "今月の利益データを集計中です。",
    risk:      "現在のリスクレベルは低〜中程度です。",
    market:    "市場は通常の変動範囲内で推移しています。",
    next:      "次の運用判断はAIが自動的に行います。",
    recommend: "現在の設定は最適化されています。引き続き安心してお任せください。",
  }
  return responses[id] ?? "ご質問ありがとうございます。データを確認中です。"
}

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
            ? "bg-zinc-800 text-white rounded-tl-none"
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
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      role: "ai",
      content:
        "こんにちは！UAT AIです。\n運用状況や市場について何でもお聞きください。",
      timestamp: new Date(),
    },
  ])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const router = useRouter()

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
  // liff-history 側は #539 で実装済みの degrade 分岐 (BrowserLoginPrompt / 自動再認証) に
  // 正しく入り、黒画面にならない。LIFF 実機では従来どおり履歴画面へ遷移する。
  const handleHistoryOpen = () => {
    onClose()
    router.push("/liff-history")
  }

  // サジェストボタンタップ → ユーザーメッセージ追加 → AI 返答取得
  const handleSuggest = async (btn: {
    id: string
    label: string
    prompt: string
  }) => {
    if (loading) return

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
          "応答を取得できませんでした"
      } else {
        // API 未実装 or エラー → プレースホルダー
        aiContent = getPlaceholderResponse(btn.id)
      }
    } catch {
      aiContent = getPlaceholderResponse(btn.id)
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
        className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-950
                   h-[88vh] rounded-t-2xl flex flex-col
                   animate-in slide-in-from-bottom duration-300"
      >
        {/* ドラッグハンドル */}
        <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
          <div className="w-8 h-1 rounded-full bg-zinc-700" />
        </div>

        {/* ヘッダー */}
        <div className="flex items-center bg-[#1a3d2e] px-4 py-3 flex-shrink-0">
          <button
            onClick={onClose}
            className="text-white mr-3 p-0.5 hover:bg-white/10 rounded transition-colors"
            aria-label="閉じる"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="text-white font-semibold text-base leading-none">
              UAT AI
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className="w-1.5 h-1.5 rounded-full bg-[#4ade9a]" />
              <span className="text-zinc-400 text-xs">オンライン</span>
            </div>
          </div>
          <button
            onClick={handleHistoryOpen}
            className="text-zinc-400 p-1 hover:text-zinc-200 hover:bg-white/10 rounded transition-colors"
            aria-label="履歴"
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
              <div className="w-7 h-7 rounded-full bg-[#1D9E75] flex items-center justify-center text-white text-xs font-bold mr-2 mt-0.5 flex-shrink-0">
                AI
              </div>
              <div className="bg-zinc-800 rounded-2xl rounded-tl-none px-4 py-2.5 max-w-[80%]">
                <div className="flex gap-1 items-center h-4">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce"
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
        <div className="flex-shrink-0 px-4 pb-6 pt-3 border-t border-zinc-800">
          <p className="text-zinc-600 text-xs mb-2">質問を選んでください</p>
          <div className="grid grid-cols-2 gap-2">
            {SUGGEST_BUTTONS.map((btn) => (
              <button
                key={btn.id}
                onClick={() => handleSuggest(btn)}
                disabled={loading}
                className="bg-zinc-800 hover:bg-zinc-700 active:bg-zinc-600 disabled:opacity-40
                           text-zinc-100 text-xs px-3 py-2.5 rounded-xl text-left transition-colors
                           border border-zinc-700 hover:border-zinc-600"
              >
                {btn.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
