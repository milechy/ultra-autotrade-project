// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/ProposalActionCard.tsx
// 保留中の AI 提案を arobix カードで表示し、承認 (→署名シート) / 見送り を提供する。
"use client"

import { useState, useEffect } from "react"
import { useTranslations } from "next-intl"
import { ArrowUp, ArrowDown } from "lucide-react"
import { liffFetch } from "@/lib/liff/liff-fetch"
import type { ChatProposal } from "./ProposalSignSheet"
import { DepositGuideInline } from "./DepositGuideInline"

interface ProposalActionCardProps {
  proposal: ChatProposal
  rejecting: boolean
  onApprove: () => void
  onReject: () => void
  // F4: wallet 残高 < 提案額のとき true。承認は有効のまま (押すと署名シートで入金導線を出す)
  // が、カードにヒントを表示して事前に気づけるようにする。
  insufficientBalance?: boolean
  // 統合ボックス化: 汎用 AI 判定ボックスの代わりにこのカードが確信度・残高を表示する。
  // confidence は proposal 自身の値ではなく直近の aiJudgment 由来（backend が
  // ChatProposal.confidence を送信しないため）。UI上に注記を出して誤解を防ぐ。
  confidence?: number
  balanceUsd: number | null
  onDepositSettled?: () => void
}

export function ProposalActionCard({
  proposal,
  rejecting,
  onApprove,
  onReject,
  insufficientBalance = false,
  confidence,
  balanceUsd,
  onDepositSettled,
}: ProposalActionCardProps) {
  const t = useTranslations("Liff")
  const [expanded, setExpanded] = useState(false)

  // operation 種別ごとの表示設定（マルチプロトコル対応 / Phase-C2）。
  const operationConfig: Record<
    string,
    { label: string; color: string; icon: typeof ArrowUp }
  > = {
    SUPPLY: { label: t("exec.supply"), color: "text-[#1D9E75]", icon: ArrowUp },
    WITHDRAW: { label: t("exec.withdraw"), color: "text-red-600", icon: ArrowDown },
    STAKE_ETH: { label: t("exec.stakeEth"), color: "text-[#1D9E75]", icon: ArrowUp },
    UNSTAKE_ETH: { label: t("exec.unstakeEth"), color: "text-red-600", icon: ArrowDown },
    BUY_PT: { label: t("exec.buyPt"), color: "text-[#1D9E75]", icon: ArrowUp },
    SELL_PT: { label: t("exec.sellPt"), color: "text-red-600", icon: ArrowDown },
  }
  const config = operationConfig[proposal.operation] ?? operationConfig["SUPPLY"]
  const OperationIcon = config.icon

  // 統合ボックス化で汎用 AI 判定ボックス(BUY/SELLを text-2xl で大きく表示)が非表示に
  // なったため、代わりにこのカード自身で BUY/SELL を一番目立つ位置に大きく出す。
  // aiJudgment.action(直近の別ティック判定)ではなく、この提案自身の operation から
  // 判定する(マルチプロトコルで判定と提案がズレるリスクを避けるため確信度と同じ理由)。
  const isInflowOperation = ["SUPPLY", "STAKE_ETH", "BUY_PT"].includes(proposal.operation)
  const bigActionLabel = isInflowOperation ? "BUY" : "SELL"

  // MARKET-B: lido/pendle 提案のときのみ ETH/USD を取得してバッジ表示する。
  const isEthProposal = proposal.protocol === "lido" || proposal.protocol === "pendle"
  const [ethUsd, setEthUsd] = useState<string | null>(null)
  useEffect(() => {
    if (!isEthProposal) return
    liffFetch("/api/market/prices")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setEthUsd(d?.eth_usd ?? null))
      .catch(() => {})
  }, [isEthProposal])

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
        <span className={`flex items-center gap-1 text-sm font-bold ${config.color}`}>
          <OperationIcon className="w-4 h-4" />
          {config.label}
        </span>
        <span className="text-[#1c1a27] text-sm font-semibold">{proposal.asset}</span>
        <div className="ml-auto flex items-center gap-1.5">
          {/* MARKET-B: ETH 価格バッジ（lido/pendle 提案時のみ / API 失敗時はサイレントスキップ） */}
          {isEthProposal && ethUsd && (
            <span className="text-xs text-[#736f7e] bg-[#1c1a27]/5 px-2 py-0.5 rounded-full">
              1 ETH ≈ ${Number(ethUsd).toLocaleString("en-US", { maximumFractionDigits: 0 })}
            </span>
          )}
          {/* Phase-C2: protocol バッジ（aave 以外のとき表示） */}
          {proposal.protocol && proposal.protocol !== "aave" && (
            <span className="text-xs bg-[#1c1a27]/10 px-2 py-0.5 rounded-full text-[#736f7e]">
              {proposal.protocol}
            </span>
          )}
        </div>
      </div>

      {/* BUY/SELL 大表示（旧 AI 判定ボックスの action 表示を踏襲。一番目立たせる） */}
      <div className={`font-bold text-2xl mb-1 ${config.color}`}>{bigActionLabel}</div>

      {/* amount */}
      <div className="mb-2">
        <span className="text-[#1c1a27] text-2xl font-bold">{amountUsd}</span>
        <span className="text-[#736f7e] text-xs ml-1">
          ({amountFormatted} {proposal.asset})
        </span>
      </div>

      {/* 確信度（統合ボックス化: 直近の aiJudgment 由来。この提案固有の値ではない旨を注記） */}
      {confidence != null && (
        <p className="text-[#736f7e] text-xs mb-2">
          {confidence}% {t("home.confidenceLabel")}
          <span className="ml-1">({t("exec.confidenceNote")})</span>
        </p>
      )}

      {/* ウォレット残高（統合ボックス化: page.tsx の KPI-E 行をここに集約） */}
      <div className="flex items-center justify-between px-3 py-2 mb-3 rounded-lg bg-[#1c1a27]/5">
        <span className="text-xs text-[#736f7e]">{t("kpi.walletBalance")}</span>
        <span className="text-sm font-semibold text-[#1c1a27]">
          {balanceUsd != null
            ? `$${balanceUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : "—"}
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

      {/* F4: 残高不足ヒント (承認は有効・押すと awaiting_funds へ)。承認前から入金導線を
          ボックス内に表示し、別パネルへ遷移せず Privy fundWallet を直接起動できるようにする。 */}
      {insufficientBalance && (
        <>
          <p className="text-amber-700 text-xs mb-2">{t("exec.insufficientBalance")}</p>
          <DepositGuideInline
            shortfallUsd={
              balanceUsd != null ? Number(proposal.amount_usd) - balanceUsd : undefined
            }
            onSettled={onDepositSettled}
          />
        </>
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
