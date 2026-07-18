// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/_components/BrowserLoginPrompt.tsx
//
// ブラウザ PWA モード (LIFF degrade) で JWT が無いときに表示する優しいログイン導線。
// partner の IT リテラシを前提に、専門用語を避け、エラーも次の行動が分かる文言にする。
"use client";

import { Loader2, Wallet } from "lucide-react";
import { useTranslations } from "next-intl";
import { useLiffBrowserAuth } from "@/hooks/useLiffBrowserAuth";
import { isLiffConfigured } from "@/lib/liff/init";

interface BrowserLoginPromptProps {
  /** ログイン成功後の処理。未指定ならページをリロードして token を読み直す。 */
  onSuccess?: () => void;
}

export function BrowserLoginPrompt({ onSuccess }: BrowserLoginPromptProps) {
  const t = useTranslations("LiffBrowserLoginPrompt");
  const { signIn, signingIn, error } = useLiffBrowserAuth();

  async function handleLogin() {
    const result = await signIn();
    // login-opened / rejected / error はいずれもここでは何もしない
    // （error 文言は hook 側が setError 済み。login-opened は文言なしでモーダルを待つ）。
    if (!result.ok) return;
    if (onSuccess) {
      onSuccess();
    } else if (typeof window !== "undefined") {
      window.location.reload();
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-dvh ax-bg-app px-6 text-center">
      <Wallet className="h-10 w-10 text-[#1D9E75] mb-4" />
      <h2 className="ax-text-primary text-base font-semibold mb-2">
        {t("title")}
      </h2>
      <p className="ax-text-secondary text-sm mb-6 leading-relaxed">
        {t("description")}
      </p>

      <button
        onClick={handleLogin}
        disabled={signingIn}
        className="w-full max-w-xs flex items-center justify-center gap-2
                   bg-[#1D9E75] hover:bg-[#1a8f6a] disabled:opacity-50
                   disabled:cursor-not-allowed text-white font-semibold
                   py-3 rounded-xl transition-colors"
      >
        {signingIn ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Wallet className="h-4 w-4" />
        )}
        {signingIn ? t("signingIn") : t("loginButton")}
      </button>

      {error && <p className="text-red-600 text-xs mt-3 max-w-xs">{error}</p>}

      {isLiffConfigured() && (
        <p className="ax-text-secondary opacity-70 text-xs mt-6 leading-relaxed">
          {t("lineAppHint")}
        </p>
      )}
    </div>
  );
}
