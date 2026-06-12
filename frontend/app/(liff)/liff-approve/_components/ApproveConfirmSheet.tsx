// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/ApproveConfirmSheet.tsx
// bottom sheet: proposal 確認 → Privy 署名 → POST approve
"use client";

import { useState, useCallback } from "react";
import { usePrivy, useWallets } from "@privy-io/react-auth";
import { useTranslations } from "next-intl";
import { ethers } from "ethers";
import { Loader2, Lock } from "lucide-react";
import {
  TransactionStatus,
  type ProposalStatus,
} from "@/app/user/approve/_components/TransactionStatus";
import { buildPartnerTx, submitPartnerTx } from "@/lib/api/admin-proposals";
import type { Proposal } from "./ProposalBubble";

type SigningStatus = "idle" | "signing" | "confirming" | "success" | "error";

const signingToProposalStatus: Record<SigningStatus, ProposalStatus> = {
  idle: "pending",
  signing: "approving",
  confirming: "confirming",
  success: "success",
  error: "failed",
};

interface ApproveConfirmSheetProps {
  proposal: Proposal;
  token: string;
  open: boolean;
  onClose: () => void;
  onApproved: (txHash: string) => void;
}

export function ApproveConfirmSheet({
  proposal,
  token,
  open,
  onClose,
  onApproved,
}: ApproveConfirmSheetProps) {
  const { login } = usePrivy();
  const { wallets } = useWallets();
  const t = useTranslations("Liff.approve.confirmSheet");
  const [signingStatus, setSigningStatus] = useState<SigningStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const amountUsd = Number(proposal.amount_usd).toLocaleString("ja-JP", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
  const amountFormatted = Number(proposal.amount).toLocaleString("ja-JP", {
    maximumFractionDigits: 4,
  });
  const hfAfter = proposal.expected_hf_after
    ? Number(proposal.expected_hf_after).toFixed(2)
    : null;
  const hfCurrent = proposal.current_hf
    ? Number(proposal.current_hf).toFixed(2)
    : null;
  const hfDelta =
    hfAfter && hfCurrent
      ? (Number(hfAfter) - Number(hfCurrent)).toFixed(2)
      : null;
  const hfPositive = hfDelta !== null && Number(hfDelta) > 0;
  const gasUsd = proposal.estimated_gas_usd
    ? `~$${Number(proposal.estimated_gas_usd).toFixed(2)}`
    : null;

  const handleSignAndApprove = useCallback(async () => {
    setError(null);
    setSigningStatus("signing");

    try {
      // embedded wallet (Privy TEE) のみ使用。外部 wallet は秘密鍵管理の懸念で除外。
      const wallet = wallets.find((w) => w.walletClientType === "privy");
      if (!wallet) {
        await login();
        setSigningStatus("idle");
        return;
      }

      // Step 1: サーバーから未署名 tx を取得。
      // build-tx は onBehalfOf / to == partner 本人 wallet をサーバー側で検証して返す (§14a)。
      const txData = await buildPartnerTx(proposal.id, token);

      const eip1193 = await wallet.getEthereumProvider();
      const ethProvider = new ethers.BrowserProvider(
        eip1193 as unknown as ethers.Eip1193Provider
      );

      let finalTxHash: string;

      if (
        txData.operation === "SUPPLY" &&
        txData.approve_tx &&
        txData.supply_tx
      ) {
        // SUPPLY: approve → supply の順に partner 本人が署名・送信。
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
        })) as string;

        // approve の確定を待ってから supply を送信する。
        const approveReceipt =
          await ethProvider.waitForTransaction(approveTxHash);
        if (approveReceipt === null || approveReceipt.status === 0) {
          throw new Error(t("revertError"));
        }

        setSigningStatus("confirming");
        finalTxHash = (await eip1193.request({
          method: "eth_sendTransaction",
          params: [
            {
              to: txData.supply_tx.to,
              data: txData.supply_tx.data,
              from: txData.supply_tx.from,
              value: "0x0",
            },
          ],
        })) as string;
      } else if (txData.operation === "WITHDRAW" && txData.withdraw_tx) {
        finalTxHash = (await eip1193.request({
          method: "eth_sendTransaction",
          params: [
            {
              to: txData.withdraw_tx.to,
              data: txData.withdraw_tx.data,
              from: txData.withdraw_tx.from,
              value: "0x0",
            },
          ],
        })) as string;
      } else {
        throw new Error(t("unsupportedOperation", { operation: txData.operation }));
      }

      setSigningStatus("confirming");

      // Step 3: submit-tx で最終 tx_hash を報告。
      // サーバーが on-chain receipt を検証する (from == partner wallet / status == 1)。
      // 旧実装は /approve に tx_hash を投げるだけで receipt 検証を飛ばしていた弱点を塞ぐ (§7)。
      await submitPartnerTx(
        proposal.id,
        finalTxHash,
        txData.wallet_address,
        token
      );

      setSigningStatus("success");
      onApproved(finalTxHash);
    } catch (err) {
      setSigningStatus("error");
      const msg =
        err instanceof Error ? err.message : t("signFailed");
      setError(
        msg.includes("rejected") ? t("signCanceled") : msg
      );
    }
  }, [wallets, login, proposal.id, token, onApproved, t]);

  function handleOpenExternal() {
    const url = `https://app.ultra-auto-trade.com/partner/proposals?proposal_id=${proposal.id}&from=liff`;
    if (
      typeof window !== "undefined" &&
      (window as Window & { liff?: { openWindow: (opts: { url: string; external: boolean }) => void } }).liff
    ) {
      (window as Window & { liff?: { openWindow: (opts: { url: string; external: boolean }) => void } }).liff?.openWindow({ url, external: true });
    } else {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  }

  if (!open) return null;

  const isBusy = signingStatus === "signing" || signingStatus === "confirming";

  return (
    <>
      {/* backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60"
        onClick={!isBusy ? onClose : undefined}
      />

      {/* sheet */}
      <div className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-900 rounded-t-2xl border-t border-zinc-800 px-4 pb-8 pt-3 animate-in slide-in-from-bottom duration-300 max-h-[80vh] overflow-y-auto">
        {/* drag handle */}
        <div className="mx-auto mb-4 h-1 w-8 rounded-full bg-zinc-700" />

        <h2 className="text-base font-semibold text-zinc-100 mb-4">
          {t("title")}
        </h2>

        {/* detail rows */}
        <div className="space-y-3 mb-5">
          <DetailRow label={t("operation")}>
            <span className={proposal.operation === "SUPPLY" ? "text-green-400" : "text-red-400"}>
              {proposal.operation === "SUPPLY" ? t("supply") : t("withdraw")}
            </span>
          </DetailRow>

          <DetailRow label={t("amount")}>
            <span className="text-zinc-100 font-semibold">{amountUsd}</span>
            <span className="text-zinc-500 text-xs ml-1">
              ({amountFormatted} {proposal.asset})
            </span>
          </DetailRow>

          {hfAfter && (
            <DetailRow label={t("hfAfter")}>
              <span className={hfPositive ? "text-green-400 font-semibold" : "text-zinc-100"}>
                {hfAfter}
                {hfDelta && (
                  <span className="text-xs ml-1">
                    ({hfPositive ? "+" : ""}{hfDelta})
                  </span>
                )}
              </span>
            </DetailRow>
          )}

          {gasUsd && (
            <DetailRow label={t("gasEstimate")}>
              <span className="text-zinc-400">{gasUsd}</span>
            </DetailRow>
          )}
        </div>

        {/* signing status */}
        <TransactionStatus status={signingToProposalStatus[signingStatus]} />

        {error && (
          <p className="text-red-400 text-xs mt-2">{error}</p>
        )}

        {/* sign button */}
        <button
          onClick={handleSignAndApprove}
          disabled={isBusy || signingStatus === "success"}
          className="mt-4 w-full flex items-center justify-center gap-2 bg-green-600 hover:bg-green-500
                     disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold
                     py-3 rounded-xl transition-colors"
        >
          {isBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Lock className="h-4 w-4" />
          )}
          {isBusy ? t("processing") : signingStatus === "success" ? t("approved") : t("signApprove")}
        </button>

        {/* cancel */}
        <button
          onClick={onClose}
          disabled={isBusy}
          className="mt-2 w-full py-3 rounded-xl border border-zinc-700 text-zinc-300
                     hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed
                     text-sm font-medium transition-colors"
        >
          {t("cancel")}
        </button>

        {/* external browser fallback */}
        <div className="mt-4 text-center">
          <span className="text-zinc-600 text-xs">{t("cannotSign")}</span>
          <button
            onClick={handleOpenExternal}
            className="ml-1 text-xs text-zinc-400 underline underline-offset-2"
          >
            {t("approveInBrowser")}
          </button>
        </div>
      </div>
    </>
  );
}

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex justify-between items-baseline gap-2">
      <span className="text-xs text-zinc-500 shrink-0">{label}</span>
      <span className="text-sm text-right">{children}</span>
    </div>
  );
}
