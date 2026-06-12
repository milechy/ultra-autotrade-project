// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/InlineRejectConfirm.tsx
"use client";

import { useTranslations } from "next-intl";

interface InlineRejectConfirmProps {
  onConfirm: () => void;
  onCancel: () => void;
  disabled?: boolean;
}

export function InlineRejectConfirm({
  onConfirm,
  onCancel,
  disabled,
}: InlineRejectConfirmProps) {
  const t = useTranslations("Liff.approve.rejectConfirm");

  return (
    <div className="flex items-center justify-between gap-2 w-full animate-in fade-in duration-200">
      <p className="text-sm text-zinc-300 shrink-0">{t("prompt")}</p>
      <div className="flex gap-2 shrink-0">
        <button
          onClick={onConfirm}
          disabled={disabled}
          className="px-4 py-2 rounded-xl bg-red-700 hover:bg-red-600 disabled:opacity-50
                     text-white text-sm font-semibold transition-colors"
        >
          {t("yes")}
        </button>
        <button
          onClick={onCancel}
          disabled={disabled}
          className="px-4 py-2 rounded-xl border border-zinc-700 hover:bg-zinc-800 disabled:opacity-50
                     text-zinc-300 text-sm transition-colors"
        >
          {t("no")}
        </button>
      </div>
    </div>
  );
}
