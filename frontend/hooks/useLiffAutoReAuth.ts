// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/hooks/useLiffAutoReAuth.ts
//
// MVP-P0-12 (Asana 1215079153614242) — 7日 ITP wipe re-auth フロー
//
// LIFF idToken は LINE 側で維持されている (ITP の対象外) ため、
// localStorage の auth_token だけが ITP wipe で消えた場合は
// 「LINE 再ログイン UI を出さずに」黙って /auth/line を叩き直すことで
// ユーザー無操作で session を復元できる。
//
// 既に auth_token がある場合は何もしない (冪等)。
// LIFF が未初期化 / 非ログイン状態の場合も何もしない。

"use client";

import { useEffect, useState } from "react";

import { useLiff } from "@/hooks/useLiff";
import { recordLastSeen } from "@/lib/auth/session-monitor";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const LIFF_TOKEN_KEY = "auth_token";

export type LiffAutoReAuthState =
  | "idle" // 何もしない (token あり / LIFF 未初期化 等)
  | "reauthing" // /auth/line リクエスト中
  | "reauthed" // 再取得成功 → localStorage 更新済み
  | "failed"; // 失敗 (network / 401 等)

export type LiffAutoReAuthResult = {
  state: LiffAutoReAuthState;
  error: string | null;
};

function readLiffToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(LIFF_TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeLiffToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LIFF_TOKEN_KEY, token);
  } catch {
    // Private モード等。auto re-auth は諦め、UI に再ログイン誘導を任せる。
  }
}

/**
 * LIFF 配下で「LINE 側 idToken はあるが、自前 JWT が ITP wipe で消えた」
 * 状況を検知し、自動で /auth/line を叩き直す hook。
 *
 * 戻り値は呼び出し側 (LIFF layout 等) で状態表示や再試行に使える。
 */
export function useLiffAutoReAuth(): LiffAutoReAuthResult {
  const { isReady, isLoggedIn, idToken, profile } = useLiff();
  const [state, setState] = useState<LiffAutoReAuthState>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isReady || !isLoggedIn || !idToken || !profile) return;

    // 既に token があれば何もしない
    if (readLiffToken()) {
      setState("idle");
      return;
    }

    let cancelled = false;
    setState("reauthing");
    setError(null);

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/line`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_token: idToken,
            display_name: profile.displayName,
          }),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = (await res.json()) as { access_token?: string };
        if (cancelled) return;
        if (!data.access_token) {
          throw new Error("access_token missing in /auth/line response");
        }
        writeLiffToken(data.access_token);
        recordLastSeen();
        setState("reauthed");
      } catch (err) {
        if (cancelled) return;
        setState("failed");
        setError(
          err instanceof Error ? err.message : "LIFF 再認証に失敗しました",
        );
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isReady, isLoggedIn, idToken, profile]);

  return { state, error };
}
