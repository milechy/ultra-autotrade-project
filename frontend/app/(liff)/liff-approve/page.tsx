// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-approve/page.tsx
// LIFF内承認画面 — URL: /liff-approve
"use client";

import { useEffect, useState } from "react";
import { useLiff } from "@/hooks/useLiff";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Proposal = {
  id: number;
  operation: string;
  asset: string;
  amount: string;
  amount_usd: string;
  reason: string;
  expected_hf_after: string | null;
  estimated_gas_usd: string | null;
  status: string;
  created_at: string;
};

type ApprovalStatus = "idle" | "approving" | "rejecting" | "done" | "error";

export default function LiffApprovePage() {
  const { isReady, isLoggedIn, error } = useLiff();
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [approvalStatus, setApprovalStatus] = useState<ApprovalStatus>("idle");
  const [actionError, setActionError] = useState<string | null>(null);

  const token =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

  useEffect(() => {
    if (!isReady || !isLoggedIn || !token) return;

    setLoading(true);
    setFetchError(null);

    fetch(`${API_BASE}/api/proposals/pending`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<{ items: Proposal[]; total: number }>;
      })
      .then((data) => setProposal(data.items[0] ?? null))
      .catch((err: unknown) =>
        setFetchError(
          err instanceof Error ? err.message : "データ取得に失敗しました"
        )
      )
      .finally(() => setLoading(false));
  }, [isReady, isLoggedIn, token]);

  async function handleApprove() {
    if (!proposal || !token) return;
    setApprovalStatus("approving");
    setActionError(null);
    try {
      const r = await fetch(
        `${API_BASE}/api/proposals/${proposal.id}/approve`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${r.status}`);
      }
      setApprovalStatus("done");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "承認に失敗しました");
      setApprovalStatus("error");
    }
  }

  async function handleReject() {
    if (!proposal || !token) return;
    setApprovalStatus("rejecting");
    setActionError(null);
    try {
      const r = await fetch(
        `${API_BASE}/api/proposals/${proposal.id}/reject`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${r.status}`);
      }
      setApprovalStatus("done");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "却下に失敗しました");
      setApprovalStatus("error");
    }
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

  // --- Auth token missing (ITP によるセッション消去を含む) ---
  // isInClient かつ token なし → LIFF ログインフローを自動起動する
  if (!token) {
    if (typeof window !== 'undefined') {
      window.location.replace('/liff-login')
    }
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-950 px-4">
        <p className="text-zinc-400 text-sm">再認証中...</p>
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
            onClick={() => {
              setApprovalStatus("idle");
              setProposal(null);
            }}
            className="text-zinc-400 text-sm underline"
          >
            戻る
          </button>
        </div>
      </div>
    );
  }

  const operationColor =
    proposal?.operation === "SUPPLY"
      ? "text-green-400"
      : proposal?.operation === "WITHDRAW"
        ? "text-red-400"
        : "text-yellow-400";

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <h1 className="text-xl font-bold mb-6 text-center">取引承認</h1>

      {loading && (
        <p className="text-zinc-400 text-sm text-center">
          承認待ちの提案を取得中...
        </p>
      )}

      {fetchError && (
        <p className="text-red-400 text-sm text-center">{fetchError}</p>
      )}

      {!loading && !fetchError && proposal === null && (
        <p className="text-zinc-400 text-sm text-center">
          承認待ちの提案はありません
        </p>
      )}

      {proposal && (
        <div className="space-y-4">
          {/* Proposal card */}
          <div className="bg-zinc-900 rounded-lg p-4 space-y-3 border border-zinc-800">
            <div className="flex items-center justify-between">
              <span className="text-zinc-400 text-xs">提案 #{proposal.id}</span>
              <span className="text-zinc-500 text-xs">
                {new Date(proposal.created_at).toLocaleString("ja-JP")}
              </span>
            </div>

            <div className="flex items-center gap-3">
              <span className={`text-2xl font-bold ${operationColor}`}>
                {proposal.operation}
              </span>
              <span className="text-zinc-300 text-sm font-medium">
                {proposal.asset}
              </span>
              <span className="text-zinc-400 text-sm">
                ${Number(proposal.amount_usd).toFixed(2)}
              </span>
            </div>

            <p className="text-zinc-300 text-sm leading-relaxed">
              {proposal.reason}
            </p>

            {proposal.expected_hf_after && (
              <div className="text-zinc-500 text-xs">
                予想HF: {Number(proposal.expected_hf_after).toFixed(2)}
              </div>
            )}

            {proposal.estimated_gas_usd && (
              <div className="text-zinc-500 text-xs">
                推定ガス代: ${Number(proposal.estimated_gas_usd).toFixed(4)}
              </div>
            )}
          </div>

          {actionError && (
            <p className="text-red-400 text-sm text-center">{actionError}</p>
          )}

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
