// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-history/page.tsx
// LIFF内取引履歴 — URL: /liff-history
"use client";

import { useEffect, useState } from "react";
import { useLiff } from "@/hooks/useLiff";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PAGE_SIZE = 20;

type Decision = {
  id: number;
  query: string;
  action: string;
  confidence: number;
  reason: string | null;
  primary_provider: string;
  agreed: boolean;
  created_at: string;
};

type DecisionListResponse = {
  items: Decision[];
  total: number;
  limit: number;
  offset: number;
};

export default function LiffHistoryPage() {
  const { isReady, isLoggedIn, error } = useLiff();
  const [items, setItems] = useState<Decision[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const token =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

  useEffect(() => {
    if (!isReady || !isLoggedIn || !token) return;

    setLoading(true);
    setFetchError(null);

    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });

    fetch(`${API_BASE}/api/ai/decisions?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<DecisionListResponse>;
      })
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((err: unknown) =>
        setFetchError(
          err instanceof Error ? err.message : "データ取得に失敗しました"
        )
      )
      .finally(() => setLoading(false));
  }, [isReady, isLoggedIn, token, offset]);

  // --- Loading state ---
  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <p className="text-zinc-400 text-sm">読み込み中...</p>
      </div>
    );
  }

  // --- LIFF error ---
  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-red-400 text-sm text-center">
          LIFF初期化エラー: {error}
        </p>
      </div>
    );
  }

  // --- Not logged in ---
  if (!isLoggedIn) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-zinc-400 text-sm">LINEアプリから開いてください</p>
      </div>
    );
  }

  // --- Auth token missing ---
  if (!token) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-zinc-400 text-sm">
          認証が必要です。ログインしてください。
        </p>
      </div>
    );
  }

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <h1 className="text-xl font-bold mb-2 text-center">取引履歴</h1>
      <p className="text-zinc-500 text-xs text-center mb-6">全 {total} 件</p>

      {loading && (
        <p className="text-zinc-400 text-sm text-center py-8">読み込み中...</p>
      )}

      {fetchError && (
        <p className="text-red-400 text-sm text-center py-8">{fetchError}</p>
      )}

      {!loading && !fetchError && items.length === 0 && (
        <p className="text-zinc-400 text-sm text-center py-8">
          取引履歴がありません
        </p>
      )}

      {!loading && items.length > 0 && (
        <ul className="space-y-3">
          {items.map((item) => {
            const actionColor =
              item.action === "BUY"
                ? "text-green-400"
                : item.action === "SELL"
                  ? "text-red-400"
                  : "text-yellow-400";

            const actionBg =
              item.action === "BUY"
                ? "bg-green-900/30"
                : item.action === "SELL"
                  ? "bg-red-900/30"
                  : "bg-yellow-900/30";

            return (
              <li
                key={item.id}
                className={`rounded-lg p-3 border border-zinc-800 ${actionBg} space-y-2`}
              >
                {/* Header row */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`text-base font-bold ${actionColor}`}>
                      {item.action}
                    </span>
                    <span className="text-zinc-400 text-xs">
                      信頼度 {item.confidence}%
                    </span>
                  </div>
                  <span className="text-zinc-500 text-xs">
                    {new Date(item.created_at).toLocaleDateString("ja-JP", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>

                {/* Reason */}
                {item.reason && (
                  <p className="text-zinc-300 text-xs leading-relaxed line-clamp-2">
                    {item.reason}
                  </p>
                )}

                {/* Footer */}
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 text-xs">
                    {item.primary_provider}
                  </span>
                  {item.agreed && (
                    <span className="text-zinc-400 text-xs bg-zinc-800 px-2 py-0.5 rounded">
                      合意済
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* Pagination */}
      {!loading && total > PAGE_SIZE && (
        <div className="flex items-center justify-between pt-6">
          <button
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            disabled={!hasPrev}
            className="text-zinc-400 disabled:opacity-30 text-sm px-3 py-2 rounded-lg
                       border border-zinc-700 hover:border-zinc-500 transition-colors"
          >
            ← 前へ
          </button>

          <span className="text-zinc-500 text-xs">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
          </span>

          <button
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            disabled={!hasNext}
            className="text-zinc-400 disabled:opacity-30 text-sm px-3 py-2 rounded-lg
                       border border-zinc-700 hover:border-zinc-500 transition-colors"
          >
            次へ →
          </button>
        </div>
      )}
    </div>
  );
}
