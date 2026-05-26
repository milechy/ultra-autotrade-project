// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/hooks/useSessionMonitor.ts
//
// MVP-P0-12 (Asana 1215079153614242) — 7日 ITP wipe re-auth フロー
//
// last_seen を maintain しつつ、ITP wipe / 期限切れ近接を検知する React hook。
// AuthProvider と並走させる前提 (UI 側の専有 state なし)。

"use client";

import { useCallback, useEffect, useState } from "react";

import {
  detectSessionState,
  recordLastSeen,
  type SessionSnapshot,
} from "@/lib/auth/session-monitor";

/** 再計算間隔 (1 分)。短すぎても意味は無いが、5 日境界の検知遅延を小さくする目的。 */
const POLL_INTERVAL_MS = 60_000;

/** SSR 用デフォルト値 (hydration mismatch 回避)。 */
const INITIAL_SNAPSHOT: SessionSnapshot = {
  state: "never_seen",
  ageMs: null,
  hasToken: false,
};

export function useSessionMonitor(): SessionSnapshot {
  const [snapshot, setSnapshot] = useState<SessionSnapshot>(INITIAL_SNAPSHOT);

  const refresh = useCallback(() => {
    setSnapshot(detectSessionState());
  }, []);

  useEffect(() => {
    // マウント時に last_seen を更新し、即 state を再計算する。
    // (last_seen 更新自体が detectSessionState の結果を fresh に倒すことに注意)
    recordLastSeen();
    refresh();

    // 1 分ごとに再計算 (5/7 日境界跨ぎ検知用、軽量)
    const interval = window.setInterval(refresh, POLL_INTERVAL_MS);

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        // 戻ってきたタイミングで last_seen を更新 + 即再計算
        recordLastSeen();
        refresh();
      }
    };

    const handleStorage = (event: StorageEvent) => {
      // 他タブで token / last_seen が変化したら反映
      if (
        event.key === null ||
        event.key === "ultra_auth_token" ||
        event.key === "ultra_auth_expires" ||
        event.key === "auth_token" ||
        event.key === "ultra_last_seen"
      ) {
        refresh();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("storage", handleStorage);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("storage", handleStorage);
    };
  }, [refresh]);

  return snapshot;
}
