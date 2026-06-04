// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/hooks/useLiff.ts
"use client";

import { useEffect, useState } from "react";

export type LiffProfile = {
  userId: string;
  displayName: string;
  pictureUrl?: string;
};

export type LiffState = {
  isReady: boolean;
  /** isReady の別名（layout等との互換性） */
  isInitialized: boolean;
  isLoggedIn: boolean;
  /** LINEアプリ内で開かれているか */
  isInClient: boolean;
  profile: LiffProfile | null;
  idToken: string | null;
  error: string | null;
  /**
   * NEXT_PUBLIC_LIFF_ID が設定されているか。
   * false = ブラウザ PWA モード（LIFF SDK は初期化されず、error は LIFF 未設定では立たない）。
   * true  = LIFF モード（error は実際の liff.init 失敗時のみ立つ）。
   */
  liffConfigured: boolean;
};

export function useLiff(): LiffState {
  const [state, setState] = useState<LiffState>({
    isReady: false,
    isInitialized: false,
    isLoggedIn: false,
    isInClient: false,
    profile: null,
    idToken: null,
    error: null,
    liffConfigured: true,
  });

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const { initLiff, getLiff, isLiffConfigured } = await import(
          "@/lib/liff/init"
        );

        // ブラウザ PWA モード: LIFF_ID 未設定なら SDK を読み込まず degrade。
        // 画面はブラウザで描画され、LIFF 専用機能（profile/idToken 等）は無効。
        if (!isLiffConfigured()) {
          if (!cancelled) {
            setState({
              isReady: true,
              isInitialized: true,
              isLoggedIn: false,
              isInClient: false,
              profile: null,
              idToken: null,
              error: null,
              liffConfigured: false,
            });
          }
          return;
        }

        await initLiff();
        const liff = await getLiff();

        if (cancelled) return;

        const isLoggedIn = liff.isLoggedIn();
        const isInClient = liff.isInClient();
        if (!isLoggedIn) {
          setState((s) => ({
            ...s,
            isReady: true,
            isInitialized: true,
            isLoggedIn: false,
            isInClient,
          }));
          return;
        }

        const [profile, idToken] = await Promise.all([
          liff.getProfile(),
          Promise.resolve(liff.getIDToken()),
        ]);

        if (cancelled) return;
        setState({
          isReady: true,
          isInitialized: true,
          isLoggedIn: true,
          isInClient,
          profile: {
            userId: profile.userId,
            displayName: profile.displayName,
            pictureUrl: profile.pictureUrl,
          },
          idToken,
          error: null,
          liffConfigured: true,
        });
      } catch (err) {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            isReady: true,
            isInitialized: true,
            error:
              err instanceof Error ? err.message : "LIFF initialization failed",
          }));
        }
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
