// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-approve/page.tsx
// LIFF チャット型承認画面 — /liff-approve
"use client";

import { useEffect, useRef, useState } from "react";
import { useLiff } from "@/hooks/useLiff";
import { ChatHeader } from "./_components/ChatHeader";
import { ProposalBubble, type Proposal } from "./_components/ProposalBubble";
import {
  DecisionHistoryItem,
  type DecisionHistoryEntry,
} from "./_components/DecisionHistoryItem";
import { SystemMessageRow } from "./_components/SystemMessageRow";
import { SystemDateSeparator } from "./_components/SystemDateSeparator";
import { ActionBar, type ActionBarState } from "./_components/ActionBar";
import { ApproveConfirmSheet } from "./_components/ApproveConfirmSheet";
import { ChatLoadingSkeleton } from "./_components/ChatLoadingSkeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type SystemMsg = { id: string; text: string };

export default function LiffApprovePage() {
  const { isReady, isLoggedIn, error } = useLiff();
  const token =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [history, setHistory] = useState<DecisionHistoryEntry[]>([]);
  const [extraCount, setExtraCount] = useState(0);

  const [actionState, setActionState] = useState<ActionBarState>("idle");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [systemMsgs, setSystemMsgs] = useState<SystemMsg[]>([]);

  const bottomRef = useRef<HTMLDivElement>(null);

  // ---------- data fetch ----------
  useEffect(() => {
    if (!isReady || !isLoggedIn || !token) return;

    setLoading(true);
    setFetchError(null);

    Promise.all([
      fetch(`${API_BASE}/api/proposals/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data?.items?.length) {
            setProposal(data.items[0] as Proposal);
            setExtraCount(Math.max(0, (data.total ?? 1) - 1));
          }
        }),
      fetch(`${API_BASE}/api/ai/decisions?limit=20`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (Array.isArray(data?.items)) {
            setHistory(data.items as DecisionHistoryEntry[]);
          } else if (Array.isArray(data)) {
            setHistory(data as DecisionHistoryEntry[]);
          }
        }),
    ])
      .catch(() => setFetchError("データ取得に失敗しました"))
      .finally(() => setLoading(false));
  }, [isReady, isLoggedIn, token]);

  // scroll to bottom when proposal appears
  useEffect(() => {
    if (proposal) {
      setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    }
  }, [proposal]);

  // ---------- action handlers ----------
  function addSystemMsg(text: string) {
    const id = `sys-${Date.now()}`;
    setSystemMsgs((prev) => [...prev, { id, text }]);
  }

  async function handleRejectConfirm() {
    if (!proposal || !token) return;
    setActionState("rejecting");
    try {
      const res = await fetch(
        `${API_BASE}/api/proposals/${proposal.id}/reject`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      addSystemMsg("却下しました");
      setActionState("done");
      setProposal(null);
    } catch {
      setActionState("idle");
    }
  }

  function handleApproved(_txHash: string) {
    setSheetOpen(false);
    addSystemMsg("承認しました ✓");
    setActionState("done");
    setProposal(null);
  }

  function toDateLabel(dateStr: string) {
    return new Date(dateStr).toLocaleDateString("ja-JP", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  }

  // ---------- early returns ----------
  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-dvh bg-zinc-950">
        <p className="text-zinc-400 text-sm">読み込み中...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-dvh bg-zinc-950 px-4">
        <p className="text-red-400 text-sm text-center">
          LIFF初期化エラー: {error}
        </p>
      </div>
    );
  }

  if (!isLoggedIn) {
    return (
      <div className="flex items-center justify-center min-h-dvh bg-zinc-950 px-4">
        <p className="text-zinc-400 text-sm">LINEアプリから開いてください</p>
      </div>
    );
  }

  if (!token) {
    if (typeof window !== "undefined") {
      window.location.replace("/liff-login");
    }
    return (
      <div className="flex items-center justify-center min-h-dvh bg-zinc-950 px-4">
        <p className="text-zinc-400 text-sm">再認証中...</p>
      </div>
    );
  }

  const actionBarState: ActionBarState = proposal ? actionState : "empty";

  return (
    <div className="w-[375px] mx-auto h-dvh bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden">
      <ChatHeader token={token} />

      {/* scrollable chat area */}
      <div className="flex-1 overflow-y-auto pt-14 pb-24">
        {loading ? (
          <ChatLoadingSkeleton />
        ) : (
          <>
            {/* fetch error */}
            {fetchError && (
              <div className="px-3 py-2">
                <SystemMessageRow message={fetchError} />
                <div className="flex justify-center mt-1">
                  <button
                    onClick={() => window.location.reload()}
                    className="text-xs text-zinc-400 underline"
                  >
                    再試行
                  </button>
                </div>
              </div>
            )}

            {/* decision history with date separators */}
            {history.length > 0 && (
              <>
                {(() => {
                  let lastDate = "";
                  return history.map((item) => {
                    const dateLabel = toDateLabel(item.created_at);
                    const showSep = dateLabel !== lastDate;
                    lastDate = dateLabel;
                    return (
                      <div key={item.id}>
                        {showSep && (
                          <SystemDateSeparator date={dateLabel} />
                        )}
                        <DecisionHistoryItem item={item} />
                      </div>
                    );
                  });
                })()}
              </>
            )}

            {/* system messages (approve/reject results) */}
            {systemMsgs.map((msg) => (
              <SystemMessageRow key={msg.id} message={msg.text} />
            ))}

            {/* pending proposal bubble */}
            {proposal && (
              <>
                <SystemDateSeparator date={toDateLabel(proposal.created_at)} />
                <ProposalBubble proposal={proposal} />
                {extraCount > 0 && (
                  <p className="text-xs text-zinc-500 text-center mt-1 mb-2">
                    他に {extraCount} 件の提案があります →
                  </p>
                )}
              </>
            )}

            {/* empty state */}
            {!proposal &&
              actionState !== "done" &&
              !fetchError &&
              !loading && (
                <div className="flex flex-col items-center justify-center py-16 text-zinc-600">
                  <p className="text-sm">提案を待っています...</p>
                </div>
              )}

            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* fixed bottom action bar */}
      <ActionBar
        state={actionBarState}
        onApprove={() => setSheetOpen(true)}
        onRejectRequest={() => setActionState("reject-confirm")}
        onRejectConfirm={handleRejectConfirm}
        onRejectCancel={() => setActionState("idle")}
      />

      {/* approve confirm bottom sheet (Privy 署名フロー) */}
      {proposal && (
        <ApproveConfirmSheet
          proposal={proposal}
          token={token}
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          onApproved={handleApproved}
        />
      )}
    </div>
  );
}
