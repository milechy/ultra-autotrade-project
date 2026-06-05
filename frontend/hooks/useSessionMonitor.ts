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
  hasActiveToken,
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
    // マウント時に「認証済みの場合のみ」last_seen を更新し、即 state を再計算する。
    // last_seen は「認証済みセッションの活動時刻」を表す。未認証 (初回 incognito 等) で
    // 記録すると never_seen が wiped に化け、一般ユーザーの初回訪問で誤って
    // 「セッションが切れました」バナーが出てしまう (不適切な導線)。
    // 認証済みユーザーの token 期限切れ/wipe 検知 (#424) は、過去の認証セッションで
    // 記録済みの last_seen が残ることで従来どおり機能する。
    if (hasActiveToken()) {
      recordLastSeen();
    }
    refresh();

    // 1 分ごとに再計算 (5/7 日境界跨ぎ検知用、軽量)
    const interval = window.setInterval(refresh, POLL_INTERVAL_MS);

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        // 戻ってきたタイミングで (認証済みのみ) last_seen を更新 + 即再計算
        if (hasActiveToken()) {
          recordLastSeen();
        }
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
