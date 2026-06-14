// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-history/page.tsx
// LIFF内取引履歴 — URL: /liff-history
"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLiff } from "@/hooks/useLiff";
import { BrowserLoginPrompt } from "../_components/BrowserLoginPrompt";

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
  const t = useTranslations("LiffHistory");
  const { isReady, error, liffConfigured } = useLiff();
  const [items, setItems] = useState<Decision[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const token =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

  useEffect(() => {
    // 認証は JWT (token) の有無で判定する (ブラウザ degrade モードでも token があれば続行)。
    if (!isReady || !token) return;

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
          err instanceof Error ? err.message : t("fetchError")
        )
      )
      .finally(() => setLoading(false));
  }, [isReady, token, offset, t]);

  // --- Loading state ---
  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950">
        <p className="text-zinc-400 text-sm">{t("loading")}</p>
      </div>
    );
  }

  // --- LIFF error (LIFF モードの実 init 失敗時のみ。ブラウザ degrade では立たない) ---
  if (liffConfigured && error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-red-400 text-sm text-center">
          {t("liffInitError", { error })}
        </p>
      </div>
    );
  }

  // 黒画面の if(!isLoggedIn) ガードは (liff)/layout.tsx の中央集権 degrade ガードへ移譲済み。
  // (#548 の liff-history 個別 degrade は本対策で supersede)
  if (!token) {
    // LIFF モード: LINE idToken から JWT を発行するため liff-login へ (ITP セッション消去含む)。
    if (liffConfigured) {
      if (typeof window !== 'undefined') {
        window.location.replace('/liff-login')
      }
      return (
        <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
          <p className="text-zinc-400 text-sm">{t("reauthing")}</p>
        </div>
      );
    }
    // ブラウザ degrade モード: Privy wallet 署名で JWT を取得する。
    return <BrowserLoginPrompt />;
  }

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <h1 className="text-xl font-bold mb-2 text-center">{t("title")}</h1>
      <p className="text-zinc-500 text-xs text-center mb-6">{t("totalCount", { total })}</p>

      {loading && (
        <p className="text-zinc-400 text-sm text-center py-8">{t("loading")}</p>
      )}

      {fetchError && (
        <p className="text-red-400 text-sm text-center py-8">{fetchError}</p>
      )}

      {!loading && !fetchError && items.length === 0 && (
        <p className="text-zinc-400 text-sm text-center py-8">
          {t("noHistory")}
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
                      {t("confidence", { value: item.confidence })}
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
                      {t("agreed")}
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
            {t("prevPage")}
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
            {t("nextPage")}
          </button>
        </div>
      )}
    </div>
  );
}
