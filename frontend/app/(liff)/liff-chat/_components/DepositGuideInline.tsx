// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/DepositGuideInline.tsx
// 残高不足時にボックス内で完結させる入金導線。SBI VCトレード等の送金案内(Liff.awaitingFunds.guide
// を流用)+ Privy fundWallet() の直接起動ボタン。別パネルへの画面遷移を挟まない
// (ProposalActionCard の未承認・残高不足時、AwaitingFundsCard の入金待ち時の両方から使う)。
"use client"

import { useTranslations } from "next-intl"
import { Loader2 } from "lucide-react"
import { useDepositFundWallet } from "@/hooks/useDepositFundWallet"

interface DepositGuideInlineProps {
  /** 不足額(USD)。渡すと Privy fundWallet の初期入力額として使う。 */
  shortfallUsd?: number
  /** 入金後の残高再取得コールバック(呼び出し元の refetch)。 */
  onSettled?: () => void
}

export function DepositGuideInline({ shortfallUsd, onSettled }: DepositGuideInlineProps) {
  const t = useTranslations("Liff")
  const { trigger, isFunding } = useDepositFundWallet({ onSettled })

  return (
    <div className="mt-3 rounded-xl bg-amber-50 border border-amber-200 p-3">
      <p className="text-[#736f7e] text-xs leading-relaxed mb-3">{t("awaitingFunds.guide")}</p>
      <button
        onClick={() => { void trigger(shortfallUsd) }}
        disabled={isFunding}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-[#1D9E75]
                   active:bg-[#178a64] text-white text-sm font-bold disabled:opacity-50 transition-colors"
      >
        {isFunding && <Loader2 className="w-4 h-4 animate-spin" />}
        {t("exec.depositCta")}
      </button>
    </div>
  )
}
