// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/AwaitingFundsCard.tsx
// S2: 入金待ち(awaiting_funds)提案カード。残高不足で承認した提案を保持し、必要額/不足額/
// 入金導線を表示。バックグラウンドで残高ポーリングし、着金検知で approved 化すると
// page.tsx が自動で署名フロー(ProposalActionCard/ProposalSignSheet)へ遷移する。
"use client"

import { useTranslations } from "next-intl"
import { Loader2, Wallet } from "lucide-react"
import type { ChatProposal } from "./ProposalSignSheet"

interface AwaitingFundsCardProps {
  proposal: ChatProposal
  balanceUsd: number | null
  onDeposit: () => void
  onReject: () => void
  rejecting?: boolean
}

export function AwaitingFundsCard({
  proposal,
  balanceUsd,
  onDeposit,
  onReject,
  rejecting = false,
}: AwaitingFundsCardProps) {
  const t = useTranslations("Liff.awaitingFunds")

  const required = Number(proposal.amount_usd)
  const current = balanceUsd ?? 0
  const shortfall = Math.max(0, required - current)
  const fmt = (n: number) =>
    n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })

  return (
    <div
      role="status"
      className="ax-card-warm rounded-2xl mx-4 mt-4 p-4 border-2 border-amber-300/60"
    >
      {/* header */}
      <div className="flex items-center gap-2 mb-3">
        <Wallet className="w-4 h-4 text-amber-600" />
        <span className="text-sm font-bold text-amber-700">{t("title")}</span>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-[#736f7e]">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-500" />
          {t("detecting")}
        </span>
      </div>

      {/* amounts */}
      <div className="space-y-1.5 mb-3">
        <Row label={t("requiredAmount")} value={fmt(required)} strong />
        <Row label={t("currentBalance")} value={balanceUsd != null ? fmt(current) : "—"} />
        <Row label={t("shortfall")} value={fmt(shortfall)} amber />
      </div>

      <p className="text-[#736f7e] text-xs leading-relaxed mb-3">{t("guide")}</p>

      {/* actions */}
      <div className="flex gap-3 mt-3">
        <button
          onClick={onReject}
          disabled={rejecting}
          className="flex-1 py-2.5 rounded-xl border border-[#1c1a27]/20 text-[#1c1a27]
                     font-semibold disabled:opacity-40 transition-colors"
        >
          {t("reject")}
        </button>
        <button
          onClick={onDeposit}
          className="flex-1 py-2.5 rounded-xl bg-[#1D9E75] active:bg-[#178a64] text-white
                     font-bold transition-colors"
        >
          {t("depositCta")}
        </button>
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  strong,
  amber,
}: {
  label: string
  value: string
  strong?: boolean
  amber?: boolean
}) {
  return (
    <div className="flex justify-between items-baseline gap-2">
      <span className="text-xs text-[#736f7e]">{label}</span>
      <span
        className={
          amber
            ? "text-sm font-semibold text-amber-700"
            : strong
              ? "text-sm font-bold text-[#1c1a27]"
              : "text-sm text-[#1c1a27]"
        }
      >
        {value}
      </span>
    </div>
  )
}
