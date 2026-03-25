// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/liff/init.ts
/**
 * LIFF SDK初期化ヘルパー。
 * クライアントサイドのみで使用すること（useEffect内）。
 */

let _initialized = false;

export async function initLiff(): Promise<void> {
  if (_initialized) return;

  const liffId = process.env.NEXT_PUBLIC_LIFF_ID;
  if (!liffId) {
    throw new Error("NEXT_PUBLIC_LIFF_ID is not set");
  }

  const liff = (await import("@line/liff")).default;
  await liff.init({ liffId });
  _initialized = true;
}

export async function getLiff() {
  return (await import("@line/liff")).default;
}
