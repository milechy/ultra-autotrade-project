// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/lib/auth/token-key.ts
//
// localStorage の auth token key を一本化する単一の真実 (Asana 1215441139765963)。
//
// 背景:
//   - 書き手 (LIFF login / 再認証 / liff-chat home) は 'auth_token' に書く。
//   - 読み手の一部 (MyWalletPanel / register / lib auth 系) は 'ultra_auth_token'
//     を読んでいたため、キー不整合で 401 / 永久読込が発生していた。
//   - 正準キーは書き手側の 'auth_token' に統一する。
//
// 移行方針:
//   - getAuthToken は AUTH_TOKEN_KEY を優先し、無ければ LEGACY_AUTH_TOKEN_KEY を
//     フォールバックで読む (旧キーで保存済みの既存セッションを救済する移行シム)。
//   - setAuthToken / clearAuthToken は両キーを書く / 消すことで、旧キーを読む
//     未移行コードが残っていても整合させる (移行完了後に legacy 書き込みは除去予定)。
//
// すべて SSR セーフ (typeof window ガード必須) かつ localStorage 例外
// (Safari Private Mode / quota) を握り潰す。

/** 正準 auth token key。書き手・読み手はこのキーに収束する。 */
export const AUTH_TOKEN_KEY = "auth_token";

/** 旧 auth token key。フォールバック読み込み / 後方互換書き込み用。 */
export const LEGACY_AUTH_TOKEN_KEY = "ultra_auth_token";

function safeGet(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private モード / quota exceeded — 静かに無視する
  }
}

function safeRemove(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

/**
 * 保存済み auth token を取得する。
 * 正準キー (AUTH_TOKEN_KEY) を優先し、無ければ旧キー (LEGACY_AUTH_TOKEN_KEY) を
 * フォールバックで読む移行シム。SSR / localStorage アクセス不可時は null。
 */
export function getAuthToken(): string | null {
  return safeGet(AUTH_TOKEN_KEY) ?? safeGet(LEGACY_AUTH_TOKEN_KEY);
}

/**
 * auth token を保存する。
 * 正準キーと旧キーの両方へ同じ値を書き込み、旧キーを読む未移行コードとも整合させる。
 */
export function setAuthToken(token: string): void {
  safeSet(AUTH_TOKEN_KEY, token);
  safeSet(LEGACY_AUTH_TOKEN_KEY, token);
}

/**
 * auth token を消去する。
 * 正準キーと旧キーの両方を削除し、フォールバック読み込みで蘇らないようにする。
 */
export function clearAuthToken(): void {
  safeRemove(AUTH_TOKEN_KEY);
  safeRemove(LEGACY_AUTH_TOKEN_KEY);
}
