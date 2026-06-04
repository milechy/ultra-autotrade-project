// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/DecisionHistoryItem.tsx
"use client";

import { useRouter } from "next/navigation";
import { Check, X, ArrowUp, ArrowDown } from "lucide-react";

export type DecisionHistoryEntry = {
  id: number;
  action: string;
  confidence: number;
  agreed: boolean;
  created_at: string;
};

interface DecisionHistoryItemProps {
  item: DecisionHistoryEntry;
}

export function DecisionHistoryItem({ item }: DecisionHistoryItemProps) {
  const router = useRouter();

  const dateStr = new Date(item.created_at).toLocaleDateString("ja-JP", {
    month: "2-digit",
    day: "2-digit",
  });

  const actionColor =
    item.action === "BUY"
      ? "text-green-400"
      : item.action === "SELL"
        ? "text-red-400"
        : "text-yellow-400";

  const ActionIcon =
    item.action === "BUY" ? ArrowUp : item.action === "SELL" ? ArrowDown : null;

  return (
    <button
      onClick={() => router.push("/liff-history")}
      className="w-full h-12 flex items-center gap-2 px-3 border-b border-zinc-800/60 hover:bg-zinc-900/50 transition-colors text-left"
    >
      {ActionIcon && (
        <ActionIcon className={`h-3.5 w-3.5 shrink-0 ${actionColor}`} />
      )}
      <span className={`text-xs font-semibold shrink-0 ${actionColor}`}>
        {item.action}
      </span>
      <span className="text-xs text-zinc-500 shrink-0">{item.confidence}%</span>
      <div className="flex-1" />
      {item.agreed ? (
        <span className="flex items-center gap-0.5 text-xs text-green-500 shrink-0">
          <Check className="h-3 w-3" /> 承認済
        </span>
      ) : (
        <span className="flex items-center gap-0.5 text-xs text-red-400 shrink-0">
          <X className="h-3 w-3" /> 却下
        </span>
      )}
      <span className="text-xs text-zinc-600 shrink-0 ml-2">{dateStr}</span>
    </button>
  );
}
