// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/ProposalSignSheet.tsx
// 消費者 (liff-chat) 向け半自動実行シート: 提案確認 → Privy 自己署名 → submit-tx。
// arobix warm-light テーマ。実行配線は liff-approve の ApproveConfirmSheet と同一
// (build-tx → 本人 Privy wallet 署名 → submit-tx で on-chain receipt 検証)。
"use client"

import { useState, useCallback } from "react"
import { usePrivy, useWallets } from "@privy-io/react-auth"
import { useSmartWallets } from "@privy-io/react-auth/smart-wallets"
import { useTranslations } from "next-intl"
import { ethers } from "ethers"
import { Loader2, Lock, CheckCircle2 } from "lucide-react"
import { buildPartnerTx, submitPartnerTx, type UnsignedTx } from "@/lib/api/admin-proposals"

// build-tx の UnsignedTx を Smart Wallet UserOp の call 形式 (to/data/value) に変換する。
// approve/supply/withdraw はいずれも 0 ETH value。
function toCall(tx: UnsignedTx): { to: `0x${string}`; data: `0x${string}`; value: bigint } {
  return {
    to: tx.to as `0x${string}`,
    data: tx.data as `0x${string}`,
    value: 0n,
  }
}

// /api/proposals/pending の要素 (ProposalResponse) のうち本シートが使う最小集合。
// Decimal 系は JSON では文字列で返る (CLAUDE.md: Decimal は文字列で返却)。
// confidence は ai_decision 由来で ProposalResponse には含まれないため optional。
export interface ChatProposal {
  id: number
  operation: "SUPPLY" | "WITHDRAW"
  asset: string
  amount: string
  amount_usd: string
  reason: string
  expected_hf_after: string | null
  estimated_gas_usd: string | null
  confidence?: number
  status: string
  created_at: string
}

type SigningStatus = "idle" | "signing" | "confirming" | "success" | "error"

interface ProposalSignSheetProps {
  proposal: ChatProposal
  token: string
  open: boolean
  onClose: () => void
  onExecuted: (txHash: string) => void
}

export function ProposalSignSheet({
  proposal,
  token,
  open,
  onClose,
  onExecuted,
}: ProposalSignSheetProps) {
  const { login } = usePrivy()
  const { wallets } = useWallets()
  // Smart Wallet (AA) client。設定済 (SCW ユーザー) なら UserOp 経路、未設定なら EOA 経路。
  const { client: scwClient } = useSmartWallets()
  const t = useTranslations("Liff.exec")
  const [signingStatus, setSigningStatus] = useState<SigningStatus>("idle")
  const [error, setError] = useState<string | null>(null)

  const amountUsd = Number(proposal.amount_usd).toLocaleString("ja-JP", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  })
  const amountFormatted = Number(proposal.amount).toLocaleString("ja-JP", {
    maximumFractionDigits: 4,
  })
  const hfAfter = proposal.expected_hf_after
    ? Number(proposal.expected_hf_after).toFixed(2)
    : null
  const gasUsd = proposal.estimated_gas_usd
    ? `~$${Number(proposal.estimated_gas_usd).toFixed(2)}`
    : null

  const handleSignAndExecute = useCallback(async () => {
    setError(null)
    setSigningStatus("signing")

    try {
      // Step 1: サーバーから未署名 tx を取得。build-tx は onBehalfOf / to == 本人 wallet
      // (EOA または Smart Wallet) をサーバー側で検証して返す (非カストディアル)。
      const txData = await buildPartnerTx(proposal.id, token)

      let finalHash: string

      if (scwClient) {
        // ── Smart Wallet (ERC-4337 AA) 経路: ガスは paymaster が肩代わり (ETH 不要)。──
        // approve + supply は 1 UserOp にバッチ。返り値は userOpHash → submit-tx (slice3b) が
        // bundler の eth_getUserOperationReceipt で success / sender(=SCW) を検証する。
        let calls: { to: `0x${string}`; data: `0x${string}`; value: bigint }[]
        if (txData.operation === "SUPPLY" && txData.approve_tx && txData.supply_tx) {
          calls = [toCall(txData.approve_tx), toCall(txData.supply_tx)]
        } else if (txData.operation === "WITHDRAW" && txData.withdraw_tx) {
          calls = [toCall(txData.withdraw_tx)]
        } else {
          throw new Error(t("unsupportedOperation", { operation: txData.operation }))
        }
        setSigningStatus("confirming")
        finalHash = await scwClient.sendUserOperation({ calls })
      } else {
        // ── EOA 経路 (従来・unchanged): 本人が ETH ガスを払って eth_sendTransaction。──
        // Privy embedded wallet (TEE) のみ。外部 wallet は秘密鍵管理懸念で除外。
        const wallet = wallets.find((w) => w.walletClientType === "privy")
        if (!wallet) {
          await login()
          setSigningStatus("idle")
          return
        }
        const eip1193 = await wallet.getEthereumProvider()
        const ethProvider = new ethers.BrowserProvider(
          eip1193 as unknown as ethers.Eip1193Provider,
        )

        if (txData.operation === "SUPPLY" && txData.approve_tx && txData.supply_tx) {
          const approveTxHash = (await eip1193.request({
            method: "eth_sendTransaction",
            params: [
              {
                to: txData.approve_tx.to,
                data: txData.approve_tx.data,
                from: txData.approve_tx.from,
                value: "0x0",
              },
            ],
          })) as string

          const approveReceipt = await ethProvider.waitForTransaction(approveTxHash)
          if (approveReceipt === null || approveReceipt.status === 0) {
            throw new Error(t("revertError"))
          }

          setSigningStatus("confirming")
          finalHash = (await eip1193.request({
            method: "eth_sendTransaction",
            params: [
              {
                to: txData.supply_tx.to,
                data: txData.supply_tx.data,
                from: txData.supply_tx.from,
                value: "0x0",
              },
            ],
          })) as string
        } else if (txData.operation === "WITHDRAW" && txData.withdraw_tx) {
          finalHash = (await eip1193.request({
            method: "eth_sendTransaction",
            params: [
              {
                to: txData.withdraw_tx.to,
                data: txData.withdraw_tx.data,
                from: txData.withdraw_tx.from,
                value: "0x0",
              },
            ],
          })) as string
        } else {
          throw new Error(t("unsupportedOperation", { operation: txData.operation }))
        }
      }

      setSigningStatus("confirming")

      // Step 3: submit-tx で最終 hash を報告。SCW ユーザーは userOpHash を bundler receipt で、
      // EOA ユーザーは tx_hash を on-chain receipt で検証する (slice3b の経路分岐)。
      await submitPartnerTx(proposal.id, finalHash, txData.wallet_address, token)

      setSigningStatus("success")
      onExecuted(finalHash)
    } catch (err) {
      setSigningStatus("error")
      const msg = err instanceof Error ? err.message : t("signFailed")
      setError(msg.includes("rejected") ? t("signCanceled") : msg)
    }
  }, [scwClient, wallets, login, proposal.id, token, onExecuted, t])

  if (!open) return null

  const isBusy = signingStatus === "signing" || signingStatus === "confirming"
  const isSupply = proposal.operation === "SUPPLY"

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div
        className="absolute inset-0 bg-black/60"
        onClick={!isBusy ? onClose : undefined}
      />
      <div className="relative w-[375px] mx-auto ax-card-warm rounded-t-2xl p-5 ax-safe-bottom max-h-[85vh] overflow-y-auto">
        {/* drag handle */}
        <div className="mx-auto mb-4 h-1 w-8 rounded-full bg-[#1c1a27]/15" />

        <h3 className="text-[#1c1a27] font-bold text-lg mb-4">{t("signConfirmTitle")}</h3>

        {/* detail rows */}
        <div className="space-y-3 mb-4">
          <DetailRow label={t("operation")}>
            <span className={isSupply ? "text-[#1D9E75] font-semibold" : "text-red-600 font-semibold"}>
              {isSupply ? t("supply") : t("withdraw")}
            </span>
          </DetailRow>
          <DetailRow label={t("amount")}>
            <span className="text-[#1c1a27] font-semibold">{amountUsd}</span>
            <span className="text-[#736f7e] text-xs ml-1">
              ({amountFormatted} {proposal.asset})
            </span>
          </DetailRow>
          {hfAfter && (
            <DetailRow label={t("hfAfter")}>
              <span className="text-[#1c1a27]">{hfAfter}</span>
            </DetailRow>
          )}
          {gasUsd && (
            <DetailRow label={t("gasEstimate")}>
              <span className="text-[#736f7e]">{gasUsd}</span>
            </DetailRow>
          )}
        </div>

        {/* signing status */}
        {(signingStatus === "signing" || signingStatus === "confirming") && (
          <div className="flex items-center gap-2 text-sm text-[#736f7e] mb-3">
            <Loader2 className="h-4 w-4 animate-spin text-[#1D9E75]" />
            <span>{signingStatus === "signing" ? t("requestingSignature") : t("waitingConfirmation")}</span>
          </div>
        )}
        {signingStatus === "success" && (
          <div className="flex items-center gap-2 text-sm mb-3">
            <CheckCircle2 className="h-4 w-4 text-[#1D9E75]" />
            <span className="text-[#1D9E75] font-medium">{t("txSuccess")}</span>
          </div>
        )}
        {error && <p className="text-red-600 text-xs mb-3">{error}</p>}

        {/* sign button */}
        <button
          onClick={handleSignAndExecute}
          disabled={isBusy || signingStatus === "success"}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-[#1D9E75]
                     active:bg-[#178a64] text-white font-bold disabled:opacity-50 transition-colors"
        >
          {isBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Lock className="h-4 w-4" />
          )}
          {isBusy ? t("processing") : signingStatus === "success" ? t("executed") : t("signExecute")}
        </button>

        {/* cancel */}
        <button
          onClick={onClose}
          disabled={isBusy}
          className="mt-2 w-full py-3 rounded-xl border border-[#1c1a27]/20 text-[#1c1a27]
                     font-semibold disabled:opacity-40 transition-colors"
        >
          {t("cancel")}
        </button>
      </div>
    </div>
  )
}

function DetailRow({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex justify-between items-baseline gap-2">
      <span className="text-xs text-[#736f7e] shrink-0">{label}</span>
      <span className="text-sm text-right">{children}</span>
    </div>
  )
}
