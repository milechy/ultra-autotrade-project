// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/_components/BrowserLoginPrompt.tsx
//
// ブラウザ PWA モード (LIFF degrade) で JWT が無いときに表示する優しいログイン導線。
// partner の IT リテラシを前提に、専門用語を避け、エラーも次の行動が分かる文言にする。
"use client";

import { Loader2, Wallet } from "lucide-react";
import { useLiffBrowserAuth } from "@/hooks/useLiffBrowserAuth";

interface BrowserLoginPromptProps {
  /** ログイン成功後の処理。未指定ならページをリロードして token を読み直す。 */
  onSuccess?: () => void;
}

export function BrowserLoginPrompt({ onSuccess }: BrowserLoginPromptProps) {
  const { signIn, signingIn, error } = useLiffBrowserAuth();

  async function handleLogin() {
    const ok = await signIn();
    if (!ok) return;
    if (onSuccess) {
      onSuccess();
    } else if (typeof window !== "undefined") {
      window.location.reload();
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-dvh bg-zinc-950 px-6 text-center">
      <Wallet className="h-10 w-10 text-green-500 mb-4" />
      <h2 className="text-zinc-100 text-base font-semibold mb-2">
        ログインが必要です
      </h2>
      <p className="text-zinc-400 text-sm mb-6 leading-relaxed">
        ご自身のウォレットでログインすると、
        <br />
        提案の確認と承認ができます。
      </p>

      <button
        onClick={handleLogin}
        disabled={signingIn}
        className="w-full max-w-xs flex items-center justify-center gap-2
                   bg-green-600 hover:bg-green-500 disabled:opacity-50
                   disabled:cursor-not-allowed text-white font-semibold
                   py-3 rounded-xl transition-colors"
      >
        {signingIn ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Wallet className="h-4 w-4" />
        )}
        {signingIn ? "ログイン中..." : "ウォレットでログイン"}
      </button>

      {error && <p className="text-red-400 text-xs mt-3 max-w-xs">{error}</p>}

      <p className="text-zinc-600 text-xs mt-6 leading-relaxed">
        LINEアプリからご利用の場合は、
        <br />
        メニューから開き直してください。
      </p>
    </div>
  );
}
