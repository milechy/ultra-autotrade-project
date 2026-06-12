// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/ActionBar.tsx
"use client";

import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { InlineRejectConfirm } from "./InlineRejectConfirm";

export type ActionBarState =
  | "idle"
  | "reject-confirm"
  | "approving"
  | "rejecting"
  | "done"
  | "empty";

interface ActionBarProps {
  state: ActionBarState;
  onApprove: () => void;
  onRejectRequest: () => void;
  onRejectConfirm: () => void;
  onRejectCancel: () => void;
}

export function ActionBar({
  state,
  onApprove,
  onRejectRequest,
  onRejectConfirm,
  onRejectCancel,
}: ActionBarProps) {
  const t = useTranslations("Liff.approve.actionBar");

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-20 bg-zinc-950/95 backdrop-blur-sm
                 border-t border-zinc-800 px-4 py-3"
      style={{ paddingBottom: "calc(0.75rem + env(safe-area-inset-bottom))" }}
    >
      {state === "empty" || state === "done" ? (
        <div className="flex items-center justify-center h-12">
          <p className="text-sm text-zinc-600">
            {state === "done" ? t("newWaiting") : t("waiting")}
          </p>
        </div>
      ) : state === "reject-confirm" ? (
        <div className="h-12 flex items-center">
          <InlineRejectConfirm
            onConfirm={onRejectConfirm}
            onCancel={onRejectCancel}
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 h-12">
          {/* 却下 */}
          <button
            onClick={onRejectRequest}
            disabled={state === "approving" || state === "rejecting"}
            className="flex items-center justify-center gap-1.5 rounded-xl border border-red-700
                       text-red-400 text-sm font-semibold hover:bg-red-900/20
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors h-full"
          >
            {state === "rejecting" ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> {t("rejecting")}</>
            ) : (
              t("reject")
            )}
          </button>

          {/* 承認 */}
          <button
            onClick={onApprove}
            disabled={state === "approving" || state === "rejecting"}
            className="flex items-center justify-center gap-1.5 rounded-xl bg-green-600
                       hover:bg-green-500 text-white text-sm font-semibold
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors h-full"
          >
            {state === "approving" ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> {t("approving")}</>
            ) : (
              t("approve")
            )}
          </button>
        </div>
      )}
    </div>
  );
}
