'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/components/SessionExpiryBanner.tsx
//
// MVP-P0-12 (Asana 1215079153614242) — 7日 ITP wipe re-auth フロー
//
// session 期限切れ近接 / wipe を検知したらバナーを出し、ログイン画面へ誘導する。
// LIFF / PWA 共通で使えるよう、router 依存を持たず href リンクで遷移する。

"use client";

import { useTranslations } from "next-intl";
import { useSessionMonitor } from "@/hooks/useSessionMonitor";
import { describeSessionState } from "@/lib/auth/session-monitor";

export type SessionExpiryBannerProps = {
  /**
   * 再ログイン誘導先 URL。
   * - PWA: "/login"
   * - LIFF: "/liff-login"
   * デフォルトは "/login" (PWA)。
   */
  loginHref?: string;
};

export function SessionExpiryBanner({
  loginHref = "/login",
}: SessionExpiryBannerProps) {
  const t = useTranslations("SharedSessionExpiry");
  const snapshot = useSessionMonitor();
  const message = describeSessionState(snapshot);

  // fresh / never_seen は何も出さない
  if (!message) return null;

  const isCritical =
    snapshot.state === "wiped" || snapshot.state === "expired";

  return (
    <div
      role="alert"
      data-testid="session-expiry-banner"
      data-session-state={snapshot.state}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9998,
        background: isCritical ? "#dc2626" : "#f59e0b",
        color: "#fff",
        padding: "10px 16px",
        fontSize: 14,
        textAlign: "center",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
      }}
    >
      <span>{message}</span>
      <a
        href={loginHref}
        style={{
          background: "#fff",
          color: isCritical ? "#dc2626" : "#b45309",
          borderRadius: 4,
          padding: "4px 10px",
          fontSize: 12,
          fontWeight: 600,
          textDecoration: "none",
        }}
      >
        {t("relogin")}
      </a>
    </div>
  );
}
