// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-approve/page.tsx
// LIFF内承認画面 — URL: /liff-approve
"use client";

import { useEffect, useState } from "react";
import { useLiff } from "@/hooks/useLiff";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

type ApprovalStatus = "idle" | "approving" | "rejecting" | "done" | "error";

export default function LiffApprovePage() {
  const { isReady, isLoggedIn, error } = useLiff();
  const [latest, setLatest] = useState<Decision | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [approvalStatus, setApprovalStatus] = useState<ApprovalStatus>("idle");

  const token =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

  useEffect(() => {
    if (!isReady || !isLoggedIn || !token) return;

    setLoading(true);
    setFetchError(null);

    fetch(`${API_BASE}/api/ai/decisions/latest`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Decision>;
      })
      .then((data) => setLatest(data))
      .catch((err: unknown) =>
        setFetchError(
          err instanceof Error ? err.message : "データ取得に失敗しました"
        )
      )
      .finally(() => setLoading(false));
  }, [isReady, isLoggedIn, token]);

  function handleApprove() {
    setApprovalStatus("approving");
    // 承認アクション: 実装はバックエンドAPIに依存。現時点はUIフローのみ。
    setTimeout(() => setApprovalStatus("done"), 800);
  }

  function handleReject() {
    setApprovalStatus("rejecting");
    setTimeout(() => setApprovalStatus("done"), 800);
  }

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

  // --- Done ---
  if (approvalStatus === "done") {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <div className="text-center space-y-2">
          <p className="text-green-400 text-lg font-semibold">完了しました</p>
          <button
            onClick={() => setApprovalStatus("idle")}
            className="text-zinc-400 text-sm underline"
          >
            戻る
          </button>
        </div>
      </div>
    );
  }

  const actionColor =
    latest?.action === "BUY"
      ? "text-green-400"
      : latest?.action === "SELL"
        ? "text-red-400"
        : "text-yellow-400";

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <h1 className="text-xl font-bold mb-6 text-center">取引承認</h1>

      {loading && (
        <p className="text-zinc-400 text-sm text-center">
          最新の判定を取得中...
        </p>
      )}

      {fetchError && (
        <p className="text-red-400 text-sm text-center">{fetchError}</p>
      )}

      {!loading && !fetchError && latest === null && (
        <p className="text-zinc-400 text-sm text-center">
          承認待ちの判定はありません
        </p>
      )}

      {latest && (
        <div className="space-y-4">
          {/* Decision card */}
          <div className="bg-zinc-900 rounded-lg p-4 space-y-3 border border-zinc-800">
            <div className="flex items-center justify-between">
              <span className="text-zinc-400 text-xs">判定 #{latest.id}</span>
              <span className="text-zinc-500 text-xs">
                {new Date(latest.created_at).toLocaleString("ja-JP")}
              </span>
            </div>

            <div className="flex items-center gap-3">
              <span className={`text-2xl font-bold ${actionColor}`}>
                {latest.action}
              </span>
              <span className="text-zinc-400 text-sm">
                信頼度: {latest.confidence}%
              </span>
            </div>

            {latest.reason && (
              <p className="text-zinc-300 text-sm leading-relaxed">
                {latest.reason}
              </p>
            )}

            <div className="text-zinc-500 text-xs">
              AI: {latest.primary_provider} /{" "}
              {latest.agreed ? "合意済み" : "単独判定"}
            </div>

            <div className="bg-zinc-800 rounded p-3">
              <p className="text-zinc-400 text-xs font-medium mb-1">クエリ</p>
              <p className="text-zinc-300 text-sm break-words">
                {latest.query}
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              onClick={handleApprove}
              disabled={
                approvalStatus === "approving" ||
                approvalStatus === "rejecting"
              }
              className="bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed
                         text-white font-semibold py-3 rounded-lg transition-colors text-sm"
            >
              {approvalStatus === "approving" ? "処理中..." : "承認する"}
            </button>

            <button
              onClick={handleReject}
              disabled={
                approvalStatus === "approving" ||
                approvalStatus === "rejecting"
              }
              className="bg-red-700 hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed
                         text-white font-semibold py-3 rounded-lg transition-colors text-sm"
            >
              {approvalStatus === "rejecting" ? "処理中..." : "却下する"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
