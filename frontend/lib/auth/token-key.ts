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
 * JWT の exp(秒) を見て期限切れかを判定する。
 * decode 不能 / exp 不在時は false を返す (fail-open: 解釈できないトークンは壊さない)。
 * 最終的な失効判定は backend (401) が真実源で、本判定はクライアント側の早期検知用。
 */
function isJwtExpired(token: string): boolean {
  try {
    const part = token.split(".")[1];
    if (!part) return false;
    // base64url → base64
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(base64)) as { exp?: number };
    if (typeof payload.exp !== "number") return false;
    return payload.exp * 1000 <= Date.now();
  } catch {
    return false;
  }
}

/**
 * 保存済み auth token を取得する。
 * 正準キー (AUTH_TOKEN_KEY) を優先し、無ければ旧キー (LEGACY_AUTH_TOKEN_KEY) を
 * フォールバックで読む移行シム。SSR / localStorage アクセス不可時は null。
 *
 * 期限切れ JWT は localStorage に残っていても無効として扱い、消して null を返す。
 * 残置すると /liff-login が「ログイン済み」と誤認して /liff-chat へ押し戻し、
 * terms gate が 401 → /liff-confirm → /liff-login の無限ループ (再ログイン不能の
 * ソフトロック) を起こすため (調査: 期限切れ token で smart-link/terms-agree が 401)。
 */
export function getAuthToken(): string | null {
  const token = safeGet(AUTH_TOKEN_KEY) ?? safeGet(LEGACY_AUTH_TOKEN_KEY);
  if (token === null) return null;
  if (isJwtExpired(token)) {
    clearAuthToken();
    return null;
  }
  return token;
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
