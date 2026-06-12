// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-approve/_components/ChatHeader.tsx
"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, History } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type AutomationStatus = "RUNNING" | "PAUSED" | "STOPPED";

interface ChatHeaderProps {
  token: string | null;
}

export function ChatHeader({ token }: ChatHeaderProps) {
  const router = useRouter();
  const t = useTranslations("Liff.approve.header");
  const [status, setStatus] = useState<AutomationStatus>("RUNNING");

  const statusConfig: Record<AutomationStatus, { label: string; color: string }> = {
    RUNNING: { label: t("running"), color: "bg-green-500" },
    PAUSED: { label: t("paused"), color: "bg-yellow-500" },
    STOPPED: { label: t("stopped"), color: "bg-red-500" },
  };

  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/api/automation/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.status && data.status in statusConfig) {
          setStatus(data.status as AutomationStatus);
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  function handleBack() {
    if (typeof window !== "undefined" && (window as Window & { liff?: { closeWindow: () => void } }).liff) {
      (window as Window & { liff?: { closeWindow: () => void } }).liff?.closeWindow();
    } else {
      history.back();
    }
  }

  const { label, color } = statusConfig[status];

  return (
    <div className="fixed top-0 left-0 right-0 z-30 h-14 bg-zinc-950/95 backdrop-blur-sm border-b border-zinc-800 flex items-center px-3 gap-2">
      <button
        onClick={handleBack}
        className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors"
        aria-label={t("backAriaLabel")}
      >
        <ChevronLeft className="h-5 w-5" />
      </button>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-zinc-100 leading-none">UAT AI</p>
        <p className="text-xs text-zinc-500 mt-0.5 leading-none">{t("assistantSubtitle")}</p>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
        <span className="text-xs text-zinc-400">{label}</span>
      </div>

      <button
        onClick={() => router.push("/liff-history")}
        className="ml-1 p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors"
        aria-label={t("historyAriaLabel")}
      >
        <History className="h-4 w-4" />
      </button>
    </div>
  );
}
