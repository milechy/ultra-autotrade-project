// Copyright (c) Ultra AutoTrade. All rights reserved.
// liffFetch: LIFF パネル用の fetch ラッパー。
// 401 レスポンス時に /liff-login へリダイレクトし、サイレント無視を防ぐ。
import { getAuthToken, clearAuthToken } from "@/lib/auth/token-key"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export async function liffFetch(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const token = getAuthToken()
  const res = await fetch(API_BASE + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (token ?? ""),
      ...options?.headers,
    },
  })
  if (res.status === 401 && typeof window !== "undefined") {
    // 失効/無効トークンは消してから再ログインへ送る。消さないと /liff-login が
    // 残存トークンで「ログイン済み」と誤認し /liff-chat へ押し戻すループになる。
    clearAuthToken()
    window.location.href = "/liff-login"
  }
  return res
}
