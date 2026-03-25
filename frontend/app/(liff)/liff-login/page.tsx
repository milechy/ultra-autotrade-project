// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-login/page.tsx
"use client";

import { useEffect } from "react";
import { useLiff } from "@/hooks/useLiff";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LiffLoginPage() {
  const { isReady, isLoggedIn, profile, idToken, error } = useLiff();

  useEffect(() => {
    if (!isReady || !isLoggedIn || !idToken || !profile) return;

    // バックエンドにLINE idTokenを送信してJWTを取得
    fetch(`${API_BASE}/auth/line`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_token: idToken,
        display_name: profile.displayName,
      }),
    })
      .then((r) => r.json())
      .then((data: { access_token?: string }) => {
        if (data.access_token) {
          localStorage.setItem("auth_token", data.access_token);
          // LIFFなのでLINEアプリ内で完結 — ウィンドウクローズorリダイレクト
          window.location.href = "/";
        }
      })
      .catch(console.error);
  }, [isReady, isLoggedIn, idToken, profile]);

  if (!isReady) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-destructive">Error: {error}</p>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-muted-foreground">
        {isLoggedIn ? "認証中..." : "LINEアプリから開いてください"}
      </p>
    </div>
  );
}
