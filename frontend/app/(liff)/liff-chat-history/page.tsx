// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-chat-history/page.tsx
// チャット会話履歴 — URL: /liff-chat-history
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { useLiff } from "@/hooks/useLiff";
import { getAuthToken } from "@/lib/auth/token-key";
import { BrowserLoginPrompt } from "../_components/BrowserLoginPrompt";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const PAGE_SIZE = 50;

type ChatMessage = {
  id: number;
  role: "user" | "ai";
  content: string;
  created_at: string;
};

type ChatHistoryResponse = {
  messages: ChatMessage[];
  has_more: boolean;
};

export default function LiffChatHistoryPage() {
  const router = useRouter();
  const { isReady, error, liffConfigured } = useLiff();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const token = getAuthToken();

  const fetchHistory = async (beforeId?: number, append = false) => {
    if (!token) return;

    const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
    if (beforeId !== undefined) {
      params.set("before_id", String(beforeId));
    }

    try {
      const res = await fetch(`${API_BASE}/api/chat/history?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ChatHistoryResponse;
      if (append) {
        setMessages((prev) => [...prev, ...data.messages]);
      } else {
        setMessages(data.messages);
      }
      setHasMore(data.has_more);
    } catch (err: unknown) {
      setFetchError(
        err instanceof Error ? err.message : "データ取得に失敗しました"
      );
    }
  };

  useEffect(() => {
    if (!isReady || !token) return;

    setLoading(true);
    setFetchError(null);
    fetchHistory().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, token]);

  const handleLoadMore = async () => {
    if (!hasMore || messages.length === 0) return;
    const lastId = messages[messages.length - 1].id;
    setLoadingMore(true);
    await fetchHistory(lastId, true);
    setLoadingMore(false);
  };

  // --- ロード中 ---
  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <p className="text-zinc-400 text-sm">読み込み中...</p>
      </div>
    );
  }

  // --- LIFF エラー ---
  if (liffConfigured && error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-red-400 text-sm text-center">
          LIFF初期化エラー: {error}
        </p>
      </div>
    );
  }

  // --- 未認証 ---
  if (!token) {
    if (liffConfigured) {
      if (typeof window !== "undefined") {
        window.location.replace("/liff-login");
      }
      return (
        <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
          <p className="text-zinc-400 text-sm">再認証中...</p>
        </div>
      );
    }
    return <BrowserLoginPrompt />;
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 max-w-md mx-auto">
      {/* ヘッダー */}
      <div className="flex items-center bg-[#1a3d2e] px-4 py-3 sticky top-0 z-10">
        <button
          onClick={() => router.back()}
          className="text-white mr-3 p-0.5 hover:bg-white/10 rounded transition-colors"
          aria-label="戻る"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-white font-semibold text-base leading-none">会話履歴</div>
          <div className="text-zinc-400 text-xs mt-0.5">UAT AI とのチャット記録</div>
        </div>
      </div>

      <div className="px-4 py-6">

      {loading && (
        <p className="text-zinc-400 text-sm text-center py-8">読み込み中...</p>
      )}

      {fetchError && (
        <p className="text-red-400 text-sm text-center py-8">
          データ取得に失敗しました
        </p>
      )}

      {!loading && !fetchError && messages.length === 0 && (
        <p className="text-zinc-400 text-sm text-center py-8">
          会話履歴がありません
        </p>
      )}

      {!loading && messages.length > 0 && (
        <ul className="space-y-2">
          {messages.map((msg) => {
            const isUser = msg.role === "user";
            return (
              <li
                key={msg.id}
                className={`flex ${isUser ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
                    isUser
                      ? "bg-[#4ade9a]/20 text-zinc-100 rounded-br-sm"
                      : "bg-zinc-800 text-zinc-200 rounded-bl-sm"
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                  <p
                    className={`text-[10px] mt-1 ${
                      isUser ? "text-zinc-400 text-right" : "text-zinc-500"
                    }`}
                  >
                    {new Date(msg.created_at).toLocaleString("ja-JP", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {hasMore && (
        <div className="mt-6 text-center">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="text-sm text-zinc-400 border border-zinc-700 rounded-lg px-4 py-2
                       hover:text-zinc-200 hover:border-zinc-500 transition-colors disabled:opacity-50"
          >
            {loadingMore ? "読み込み中..." : "もっと見る"}
          </button>
        </div>
      )}
      </div>
    </div>
  );
}
