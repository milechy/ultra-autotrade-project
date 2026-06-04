// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/ProposalBubble.tsx
"use client";

import { useState } from "react";
import { ArrowUp, ArrowDown } from "lucide-react";

export type Proposal = {
  id: number;
  operation: "SUPPLY" | "WITHDRAW";
  asset: string;
  amount: string;
  amount_usd: string;
  reason: string;
  expected_hf_after: string | null;
  current_hf?: string | null;
  estimated_gas_usd: string | null;
  confidence: number;
  status: string;
  created_at: string;
};

interface ProposalBubbleProps {
  proposal: Proposal;
}

export function ProposalBubble({ proposal }: ProposalBubbleProps) {
  const [expanded, setExpanded] = useState(false);

  const timeStr = new Date(proposal.created_at).toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const amountUsd = Number(proposal.amount_usd).toLocaleString("ja-JP", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });

  const amountFormatted = Number(proposal.amount).toLocaleString("ja-JP", {
    maximumFractionDigits: 4,
  });

  const isSupply = proposal.operation === "SUPPLY";
  const operationColor = isSupply ? "text-green-400" : "text-red-400";
  const OperationIcon = isSupply ? ArrowUp : ArrowDown;
  const operationLabel = isSupply ? "SUPPLY" : "WITHDRAW";

  const hfDelta =
    proposal.expected_hf_after && proposal.current_hf
      ? (Number(proposal.expected_hf_after) - Number(proposal.current_hf)).toFixed(2)
      : null;
  const hfPositive = hfDelta !== null && Number(hfDelta) > 0;

  const reasonLines = proposal.reason.split("\n");
  const isLong = reasonLines.length > 3 || proposal.reason.length > 120;
  const displayReason = !isLong || expanded ? proposal.reason : proposal.reason.slice(0, 120) + "…";

  const gasUsd = proposal.estimated_gas_usd
    ? `~$${Number(proposal.estimated_gas_usd).toFixed(2)}`
    : null;

  const totalUsd =
    proposal.estimated_gas_usd
      ? (Number(proposal.amount_usd) + Number(proposal.estimated_gas_usd)).toLocaleString("ja-JP", {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 2,
        })
      : null;

  return (
    <div className="flex flex-col items-start px-3 py-2">
      {/* bubble */}
      <div className="max-w-[88%] bg-zinc-900 border border-zinc-800 rounded-2xl rounded-tl-sm p-3 space-y-2">
        {/* operation badge + amount */}
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1 text-sm font-bold ${operationColor}`}>
            <OperationIcon className="h-4 w-4" />
            {operationLabel}
          </span>
          <span className="text-zinc-300 text-sm font-semibold">{proposal.asset}</span>
        </div>

        <div>
          <p className="text-zinc-100 text-lg font-bold leading-none">{amountUsd}</p>
          <p className="text-zinc-500 text-xs mt-0.5">
            ({amountFormatted} {proposal.asset})
          </p>
        </div>

        {/* confidence bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-zinc-500">信頼度</span>
            <span className={proposal.confidence >= 70 ? "text-green-400" : "text-blue-400"}>
              {proposal.confidence}%
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                proposal.confidence >= 70 ? "bg-green-500" : "bg-blue-400"
              }`}
              style={{ width: `${proposal.confidence}%` }}
            />
          </div>
        </div>

        {/* reason */}
        <div>
          <p className="text-zinc-300 text-sm leading-relaxed">{displayReason}</p>
          {isLong && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-xs text-zinc-500 underline mt-0.5"
            >
              {expanded ? "閉じる" : "続きを見る"}
            </button>
          )}
        </div>

        {/* HF delta */}
        {proposal.expected_hf_after && (
          <p className="text-xs text-zinc-500">
            実行後 HF:{" "}
            {proposal.current_hf && (
              <span>{Number(proposal.current_hf).toFixed(2)} → </span>
            )}
            <span className={hfPositive ? "text-green-400" : "text-zinc-300"}>
              {Number(proposal.expected_hf_after).toFixed(2)}
            </span>
            {hfDelta !== null && (
              <span className={hfPositive ? "text-green-400" : "text-red-400"}>
                {" "}({hfPositive ? "+" : ""}{hfDelta})
              </span>
            )}
          </p>
        )}

        {/* gas + total */}
        {gasUsd && (
          <div className="space-y-0.5">
            <p className="text-xs text-zinc-600">ガス概算: {gasUsd}</p>
            {totalUsd && (
              <p className="text-xs text-zinc-400 font-medium">合計（ガス込み）: {totalUsd}</p>
            )}
          </div>
        )}
      </div>

      {/* timestamp */}
      <span className="text-[10px] text-zinc-600 mt-1 px-1">{timeStr}</span>
    </div>
  );
}
