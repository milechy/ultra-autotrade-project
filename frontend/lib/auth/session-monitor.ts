// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/lib/auth/session-monitor.ts
//
// 7日 ITP wipe re-auth フロー支援 (MVP-P0-12 / Asana 1215079153614242)。
//
// iOS WKWebView (LIFF) / Safari (PWA) の Intelligent Tracking Prevention は
// 「最後の interaction から 7 日」で localStorage / cookie を黙って消す。
// 結果:
//   - Privy / 自前 JWT が黙って失効する
//   - auto-trading の承認画面に飛ばすリンクを踏んでも 401 で弾かれる
//   - ユーザーは「自動取引が止まった」と気付かない
//
// 対策:
//   1. last_seen を localStorage に書き続ける (この値も wipe 対象だが、wipe 検知に使う)
//   2. token が消えていて last_seen がある → ITP wipe を疑い、自動再ログイン誘導
//   3. last_seen が 5-7 日経過 → 期限切れバナー表示 (能動的に再ログイン誘導)
//   4. last_seen 自体も無い → 通常の新規ユーザー扱い

const LAST_SEEN_KEY = "ultra_last_seen";

// auth.ts と同じキーを再定義 (循環 import 回避のため)。
// 値が変わったら本ファイルも更新すること。
const PRIMARY_TOKEN_KEY = "ultra_auth_token";
const PRIMARY_TOKEN_EXPIRES_KEY = "ultra_auth_expires";
const LIFF_TOKEN_KEY = "auth_token";

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

/** 期限切れバナーを出す閾値 (last_seen からの経過日数)。 */
export const NEARING_EXPIRY_DAYS = 5;

/** ITP wipe を疑う閾値 (last_seen からの経過日数)。 */
export const ITP_WIPE_DAYS = 7;

export type SessionState =
  /** 起動した端末で last_seen 記録がない (新規 / 別端末) */
  | "never_seen"
  /** last_seen 5 日未満 + token 有り */
  | "fresh"
  /** last_seen 5-7 日 + token 有り → バナー表示 */
  | "nearing_expiry"
  /** last_seen は残っているが token が無い → ITP wipe 疑い */
  | "wiped"
  /** last_seen が 7 日以上前 (token の有無を問わず) */
  | "expired";

export type SessionSnapshot = {
  state: SessionState;
  /** last_seen からの経過ミリ秒 (never_seen の場合は null) */
  ageMs: number | null;
  /** いずれかの auth token が localStorage に存在するか */
  hasToken: boolean;
};

/**
 * SSR セーフな localStorage アクセス。
 * window が無い / アクセスが拒否される (Safari Private Mode) 場合は null。
 */
function safeGetItem(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch {
    // Private モード / quota exceeded — wipe 検知は token 側で補える
    return false;
  }
}

/**
 * いずれかの auth token (主トークン or LIFF トークン) が localStorage にあるかを返す。
 * 主トークンは `ultra_auth_expires` が過去だと「無い」扱い。
 */
export function hasActiveToken(): boolean {
  const primary = safeGetItem(PRIMARY_TOKEN_KEY);
  if (primary) {
    const expires = safeGetItem(PRIMARY_TOKEN_EXPIRES_KEY);
    if (expires) {
      const parsed = parseInt(expires, 10);
      if (!Number.isNaN(parsed) && Date.now() < parsed) {
        return true;
      }
      // expires 過ぎは「無い」扱い
    } else {
      // expires が無いだけなら token 自体は有るとみなす
      return true;
    }
  }
  const liff = safeGetItem(LIFF_TOKEN_KEY);
  return Boolean(liff);
}

/**
 * 現在時刻を last_seen として記録する。
 * AuthProvider / LIFF layout のマウント時と、`visibilitychange` で呼び出すこと。
 *
 * 不変条件: last_seen は「認証済みセッションの活動時刻」のみを表す。
 * 未認証 (有効な token なし) の場合は **書き込まない**。これにより
 *   - 初回 incognito / 未ログイン訪問で ultra_last_seen が作られず never_seen を維持
 *   - 「last_seen 有 + token 無」= 過去に認証済みだった証拠 = 真の wipe (#424) と確定
 * を保証する。呼び出し側のガード漏れに対する最終防壁 (write primitive level)。
 *
 * @returns 書き込みに成功したか (未認証 / Private モードでは false)
 */
export function recordLastSeen(now: number = Date.now()): boolean {
  if (!hasActiveToken()) return false;
  return safeSetItem(LAST_SEEN_KEY, String(now));
}

/** last_seen の UNIX ms を返す。存在しない / 壊れていれば null。 */
export function getLastSeen(): number | null {
  const raw = safeGetItem(LAST_SEEN_KEY);
  if (!raw) return null;
  const parsed = parseInt(raw, 10);
  if (Number.isNaN(parsed) || parsed <= 0) return null;
  return parsed;
}

/**
 * 現在の session 状態を計算する。pure (副作用なし)。
 *
 * @param now テスト用に注入可能な現在時刻 (ms)。デフォルトは `Date.now()`。
 */
export function detectSessionState(now: number = Date.now()): SessionSnapshot {
  const lastSeen = getLastSeen();
  const hasToken = hasActiveToken();

  if (lastSeen === null) {
    return {
      state: "never_seen",
      ageMs: null,
      hasToken,
    };
  }

  const ageMs = Math.max(0, now - lastSeen);
  const ageDays = ageMs / ONE_DAY_MS;

  if (ageDays >= ITP_WIPE_DAYS) {
    return { state: "expired", ageMs, hasToken };
  }

  if (!hasToken) {
    // last_seen は残っているのに token が無い → ITP wipe 疑い
    // (ユーザーが明示的に logout した場合も含むが、再ログイン誘導は同じで良い)
    return { state: "wiped", ageMs, hasToken };
  }

  if (ageDays >= NEARING_EXPIRY_DAYS) {
    return { state: "nearing_expiry", ageMs, hasToken };
  }

  return { state: "fresh", ageMs, hasToken };
}

/**
 * SessionState に対応する人間可読メッセージ (日本語)。
 * UI コンポーネントから利用。
 */
export function describeSessionState(snapshot: SessionSnapshot): string | null {
  switch (snapshot.state) {
    case "nearing_expiry":
      return "セッションが間もなく期限切れになります。再度ログインしてください。";
    case "wiped":
      return "セッションが切れました。再度ログインしてください。";
    case "expired":
      return "7日以上アクセスがなかったためセッションが切れました。再度ログインしてください。";
    case "fresh":
    case "never_seen":
      return null;
  }
}

/**
 * テスト / リセット用。本番コードから呼ばない (logout フローは auth.ts 側で完結)。
 */
export function clearLastSeen(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LAST_SEEN_KEY);
  } catch {
    // ignore
  }
}
