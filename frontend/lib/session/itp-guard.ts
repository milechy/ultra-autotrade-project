// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/lib/session/itp-guard.ts
//
// iOS WKWebView の ITP (Intelligent Tracking Prevention) は、7日間操作がないと
// localStorage を消去する。auto-trade が黙って失敗する原因。
//
// 対策:
//   1. アプリを開くたびに last_seen を更新
//   2. 6日経過で「もうすぐ期限切れ」警告 → 再認証を促す
//   3. 7日経過で ITP によるセッション消去とみなす

export const LAST_SEEN_KEY = 'ultra_last_seen'

const ITP_EXPIRE_MS  = 7 * 24 * 60 * 60 * 1000  // 7 days — ITP threshold
const ITP_WARNING_MS = 6 * 24 * 60 * 60 * 1000  // 6 days — warn before expiry

export function updateLastSeen(): void {
  try {
    localStorage.setItem(LAST_SEEN_KEY, String(Date.now()))
  } catch {
    // storage quota error — ignore
  }
}

export function getLastSeen(): number | null {
  try {
    const v = localStorage.getItem(LAST_SEEN_KEY)
    if (!v) return null
    const n = parseInt(v, 10)
    return isNaN(n) ? null : n
  } catch {
    return null
  }
}

export function getDaysSinceLastSeen(): number | null {
  const last = getLastSeen()
  if (last === null) return null
  return (Date.now() - last) / (24 * 60 * 60 * 1000)
}

export function getHoursUntilITPExpiry(): number | null {
  const last = getLastSeen()
  if (last === null) return null
  const remainingMs = ITP_EXPIRE_MS - (Date.now() - last)
  return Math.max(0, remainingMs) / (60 * 60 * 1000)
}

/**
 * last_seen が ITP の 7 日閾値を超えているか。
 * last_seen が null（初回起動 or ITP で消去済み）の場合は false を返す。
 * ITP で消去された場合は JWT 自体も消えるため、既存の auth.ts が login 画面に誘導する。
 */
export function isSessionExpiredByITP(): boolean {
  const last = getLastSeen()
  if (last === null) return false
  return Date.now() - last >= ITP_EXPIRE_MS
}

/**
 * last_seen が 6〜7 日の「警告ゾーン」にあるか。
 * この状態でアプリを開いたユーザーに再認証を促す。
 */
export function isSessionAtRisk(): boolean {
  const last = getLastSeen()
  if (last === null) return false
  const elapsed = Date.now() - last
  return elapsed >= ITP_WARNING_MS && elapsed < ITP_EXPIRE_MS
}
