// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/ProposalActionCard.tsx
// 保留中の AI 提案を arobix カードで表示し、承認 (→署名シート) / 見送り を提供する。
"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import { ArrowUp, ArrowDown } from "lucide-react"
import type { ChatProposal } from "./ProposalSignSheet"

interface ProposalActionCardProps {
  proposal: ChatProposal
  rejecting: boolean
  onApprove: () => void
  onReject: () => void
}

export function ProposalActionCard({
  proposal,
  rejecting,
  onApprove,
  onReject,
}: ProposalActionCardProps) {
  const t = useTranslations("Liff")
  const [expanded, setExpanded] = useState(false)

  const isSupply = proposal.operation === "SUPPLY"
  const OperationIcon = isSupply ? ArrowUp : ArrowDown
  const amountUsd = Number(proposal.amount_usd).toLocaleString("ja-JP", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  })
  const amountFormatted = Number(proposal.amount).toLocaleString("ja-JP", {
    maximumFractionDigits: 4,
  })

  const reason = proposal.reason ?? ""
  const isLong = reason.length > 120
  const displayReason = !isLong || expanded ? reason : reason.slice(0, 120) + "…"

  return (
    <div className="ax-card-warm rounded-2xl mx-4 mt-4 p-4 border-2 border-[#1D9E75]/40">
      {/* header */}
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`flex items-center gap-1 text-sm font-bold ${
            isSupply ? "text-[#1D9E75]" : "text-red-600"
          }`}
        >
          <OperationIcon className="w-4 h-4" />
          {isSupply ? t("exec.supply") : t("exec.withdraw")}
        </span>
        <span className="text-[#1c1a27] text-sm font-semibold">{proposal.asset}</span>
        {(proposal.confidence ?? 0) > 0 && (
          <span className="ml-auto text-[#736f7e] text-xs">
            {proposal.confidence}% {t("home.confidenceLabel")}
          </span>
        )}
      </div>

      {/* amount */}
      <div className="mb-2">
        <span className="text-[#1c1a27] text-2xl font-bold">{amountUsd}</span>
        <span className="text-[#736f7e] text-xs ml-1">
          ({amountFormatted} {proposal.asset})
        </span>
      </div>

      {/* reason */}
      {reason && (
        <p className="text-[#736f7e] text-xs leading-relaxed mb-3 whitespace-pre-wrap">
          {displayReason}
          {isLong && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="ml-1 underline"
            >
              {expanded ? t("exec.collapse") : t("exec.expand")}
            </button>
          )}
        </p>
      )}

      {/* actions */}
      <div className="flex gap-3 mt-3">
        <button
          onClick={onReject}
          disabled={rejecting}
          className="flex-1 py-2.5 rounded-xl border border-[#1c1a27]/20 text-[#1c1a27]
                     font-semibold disabled:opacity-40 transition-colors"
        >
          {rejecting ? t("exec.rejecting") : t("home.reject")}
        </button>
        <button
          onClick={onApprove}
          disabled={rejecting}
          className="flex-1 py-2.5 rounded-xl bg-[#1D9E75] active:bg-[#178a64] text-white
                     font-bold disabled:opacity-50 transition-colors"
        >
          {t("home.approve")}
        </button>
      </div>
    </div>
  )
}
