// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-login/page.tsx
"use client";

import { useEffect } from "react";
import { useLiff } from "@/hooks/useLiff";
import { BrowserLoginPrompt } from "../_components/BrowserLoginPrompt";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LiffLoginPage() {
  const { isReady, isLoggedIn, profile, idToken, error, liffConfigured } =
    useLiff();

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
      .then((data: { access_token?: string; expires_in?: number }) => {
        if (data.access_token) {
          // token key 橋渡し (GID 1215441139765963 で ultra_auth_token に一本化予定):
          // LIFF read key (auth_token) と canonical key (ultra_auth_token) の両方へ
          // 同一 JWT を書き込む。LINE 経路もこれで ultra_auth_token を満たすため、
          // 一本化 PR は auth_token を一律に除去できる。
          localStorage.setItem("auth_token", data.access_token);
          localStorage.setItem("ultra_auth_token", data.access_token);
          if (data.expires_in) {
            localStorage.setItem(
              "ultra_auth_token_expires",
              String(Date.now() + data.expires_in * 1000)
            );
          }
          // 重要事項確認 (liff-confirm) を経由してから liff-chat へ
          window.location.href = "/liff-confirm";
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

  // ブラウザ PWA モード (NEXT_PUBLIC_LIFF_ID 未設定 = liffConfigured=false / v3 の本番形態)。
  // LINE 文脈が無いため idToken ログインは不可。代わりに Privy passwordless の
  // BrowserLoginPrompt を出す。これにより liffFetch 401 / TaxPanel / TxHistoryPanel /
  // SessionExpiryBanner 等から /liff-login へ送られたユーザーが、行き止まり
  // (「LINEアプリから開いてください」) ではなく実際にログインできる入口に着地する。
  // LINE モード (liffConfigured=true / v4) では従来どおり下の idToken 経路を使う。
  if (!liffConfigured) {
    return (
      <BrowserLoginPrompt
        onSuccess={() => {
          window.location.href = "/liff-confirm";
        }}
      />
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
