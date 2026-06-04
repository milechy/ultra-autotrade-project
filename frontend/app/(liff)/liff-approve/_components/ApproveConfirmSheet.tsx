// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/ApproveConfirmSheet.tsx
// bottom sheet: proposal 確認 → Privy 署名 → POST approve
"use client";

import { useState, useCallback } from "react";
import { usePrivy, useWallets } from "@privy-io/react-auth";
import { Loader2, Lock } from "lucide-react";
import {
  TransactionStatus,
  type ProposalStatus,
} from "@/app/user/approve/_components/TransactionStatus";
import type { Proposal } from "./ProposalBubble";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
      const wallet = wallets.find((w) => w.walletClientType === "privy");
      if (!wallet) {
        await login();
        setSigningStatus("idle");
        return;
      }

      // Step 1: 未署名 tx 取得
      const buildRes = await fetch(
        `${API_BASE}/api/proposals/${proposal.id}/build-tx`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!buildRes.ok) throw new Error(`build-tx: HTTP ${buildRes.status}`);
      const { unsigned_tx } = (await buildRes.json()) as { unsigned_tx: object };

      // Step 2: Privy embedded wallet で署名 + 送信
      const eip1193 = await wallet.getEthereumProvider();
      const txHash = (await eip1193.request({
        method: "eth_sendTransaction",
        params: [unsigned_tx],
      })) as string;

      setSigningStatus("confirming");

      // Step 3: バックエンドに tx_hash を送信して approve 完了
      const approveRes = await fetch(
        `${API_BASE}/api/proposals/${proposal.id}/approve`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ tx_hash: txHash }),
        }
      );
      if (!approveRes.ok) throw new Error(`approve: HTTP ${approveRes.status}`);

      setSigningStatus("success");
      onApproved(txHash);
    } catch (err) {
      setSigningStatus("error");
      setError(
        err instanceof Error ? err.message : "署名処理に失敗しました"
      );
    }
  }, [wallets, login, proposal.id, token, onApproved]);

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
          この提案を承認しますか？
        </h2>

        {/* detail rows */}
        <div className="space-y-3 mb-5">
          <DetailRow label="操作">
            <span className={proposal.operation === "SUPPLY" ? "text-green-400" : "text-red-400"}>
              {proposal.operation === "SUPPLY" ? "Supply (入金)" : "Withdraw (出金)"}
            </span>
          </DetailRow>

          <DetailRow label="金額">
            <span className="text-zinc-100 font-semibold">{amountUsd}</span>
            <span className="text-zinc-500 text-xs ml-1">
              ({amountFormatted} {proposal.asset})
            </span>
          </DetailRow>

          {hfAfter && (
            <DetailRow label="実行後 Health Factor">
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
            <DetailRow label="ガス概算">
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
          {isBusy ? "処理中..." : signingStatus === "success" ? "承認済み ✓" : "署名して承認"}
        </button>

        {/* cancel */}
        <button
          onClick={onClose}
          disabled={isBusy}
          className="mt-2 w-full py-3 rounded-xl border border-zinc-700 text-zinc-300
                     hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed
                     text-sm font-medium transition-colors"
        >
          キャンセル
        </button>

        {/* external browser fallback */}
        <div className="mt-4 text-center">
          <span className="text-zinc-600 text-xs">署名できない場合は</span>
          <button
            onClick={handleOpenExternal}
            className="ml-1 text-xs text-zinc-400 underline underline-offset-2"
          >
            ブラウザで承認する →
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
