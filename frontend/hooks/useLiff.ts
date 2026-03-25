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
  isLoggedIn: boolean;
  profile: LiffProfile | null;
  idToken: string | null;
  error: string | null;
};

export function useLiff(): LiffState {
  const [state, setState] = useState<LiffState>({
    isReady: false,
    isLoggedIn: false,
    profile: null,
    idToken: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const { initLiff, getLiff } = await import("@/lib/liff/init");
        await initLiff();
        const liff = await getLiff();

        if (cancelled) return;

        const isLoggedIn = liff.isLoggedIn();
        if (!isLoggedIn) {
          setState((s) => ({ ...s, isReady: true, isLoggedIn: false }));
          return;
        }

        const [profile, idToken] = await Promise.all([
          liff.getProfile(),
          Promise.resolve(liff.getIDToken()),
        ]);

        if (cancelled) return;
        setState({
          isReady: true,
          isLoggedIn: true,
          profile: {
            userId: profile.userId,
            displayName: profile.displayName,
            pictureUrl: profile.pictureUrl,
          },
          idToken,
          error: null,
        });
      } catch (err) {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            isReady: true,
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
