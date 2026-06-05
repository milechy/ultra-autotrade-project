// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/liff/init.ts
/**
 * LIFF SDK初期化ヘルパー。
 * クライアントサイドのみで使用すること（useEffect内）。
 *
 * NEXT_PUBLIC_LIFF_ID が未設定の場合は「ブラウザ PWA モード」として degrade する:
 * initLiff() は何もせず return し、画面はブラウザで描画される（LIFF 専用機能のみ無効）。
 * 将来 NEXT_PUBLIC_LIFF_ID を投入すれば従来どおり LIFF モードへ自動的に戻る。
 */

let _initialized = false;

/** NEXT_PUBLIC_LIFF_ID が設定されているか（= LIFF モードで動かすか）。 */
export function isLiffConfigured(): boolean {
  return !!process.env.NEXT_PUBLIC_LIFF_ID;
}

export async function initLiff(): Promise<void> {
  if (_initialized) return;

  const liffId = process.env.NEXT_PUBLIC_LIFF_ID;
  if (!liffId) {
    // ブラウザ PWA モード: LIFF 未設定。throw せず no-op（初期化スキップ）。
    return;
  }

  const liff = (await import("@line/liff")).default;
  await liff.init({ liffId });
  _initialized = true;
}

export async function getLiff() {
  return (await import("@line/liff")).default;
}
