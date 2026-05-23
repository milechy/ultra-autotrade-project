// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/api/user_actions.ts
//
// User action logging helper for the manual (display-only) UI.
//
// 本 helper は manual UI (`/approve` 等) における「実取引を伴わない UI 操作」
// をバックエンドの `user_actions` テーブルに記録するための fetch wrapper です。
//
// TODO(P0-6 + P2-onramp): backend `POST /api/users/actions`
//   (P0-6: user_actions_router) と P2-onramp の actions_router の merge を待つ。
//   merge 前でも UI は止まらないように、retry + offline queue で best-effort 送信する。
//
// 機能:
//  1. 指数バックオフ retry (最大 3 回)
//  2. オフライン時の in-memory queue + localStorage 永続化（タブを閉じても残る）
//  3. オンライン復帰時の自動 flush
//  4. 失敗時の構造化 error log (NEXT_PUBLIC_SENTRY_DSN があれば送信、なければ console)
//
// 設計方針:
//  - manual UI is display-only。ログ送信失敗で UI を絶対に止めない。
//  - SSR 対応: window / localStorage は guard する。
//  - queue は同一 tab 内で共有。multi-tab で多重送信が起きてもバックエンド側冪等で吸収する想定。

import { apiPost } from "./client";

export type UserActionType =
  | "manual_approve_click"
  | "manual_reject_click"
  | "manual_buy_click"
  | "manual_sell_click"
  | "onboarding_step_advance"
  | "onboarding_completed";

export interface LogUserActionInput {
  action_type: UserActionType | string;
  target_type?: string;
  target_id?: string | number;
  context_json?: Record<string, unknown>;
}

export interface UserActionResponse {
  id: number;
  action_type: string;
  created_at: string;
}

interface QueuedAction extends LogUserActionInput {
  /** queued 時刻 (ms epoch)。stale な action を捨てるため */
  queued_at: number;
  /** retry 回数 */
  attempts: number;
  /** uniq id (multi-tab dedupe を簡易化) */
  qid: string;
}

const QUEUE_STORAGE_KEY = "uata.user_actions.queue";
const MAX_RETRIES = 3;
const BASE_BACKOFF_MS = 300; // 300ms, 600ms, 1200ms (指数バックオフ)
const STALE_MS = 24 * 60 * 60 * 1000; // 24h 経過した queue は捨てる

let inMemoryQueue: QueuedAction[] = [];
let flushScheduled = false;
let onlineListenerInstalled = false;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function getSentryDsn(): string | null {
  if (typeof process === "undefined") return null;
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  return dsn && dsn.length > 0 ? dsn : null;
}

function structuredError(
  scope: string,
  message: string,
  ctx: Record<string, unknown>,
): void {
  const payload = {
    scope,
    message,
    ts: new Date().toISOString(),
    ...ctx,
  };
  // 常に console.error に構造化 JSON を吐く。Sentry DSN があれば送信を試みる。
  console.error(`[user_actions] ${scope}: ${message}`, payload);

  const dsn = getSentryDsn();
  if (!dsn || !isBrowser()) return;
  // Sentry の本格 SDK を入れる代わりに、Sentry Envelope endpoint への素朴な POST を best-effort で投げる。
  // 本格 SDK 導入は別 PR (TODO: sentry-sdk wiring)。
  try {
    // sendBeacon は非同期で UI を止めない。失敗しても無視。
    const body = JSON.stringify(payload);
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon("/_sentry_proxy", body);
    }
  } catch {
    // 何があっても UI を止めない
  }
}

function loadQueueFromStorage(): QueuedAction[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(QUEUE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as QueuedAction[];
    if (!Array.isArray(parsed)) return [];
    const now = Date.now();
    return parsed.filter(
      (q) => q && typeof q.queued_at === "number" && now - q.queued_at < STALE_MS,
    );
  } catch (err) {
    structuredError("queue_load", "failed to parse localStorage queue", {
      err: String(err),
    });
    return [];
  }
}

function persistQueue(): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(
      QUEUE_STORAGE_KEY,
      JSON.stringify(inMemoryQueue),
    );
  } catch (err) {
    // QuotaExceeded など。落とすしかないが UI は止めない。
    structuredError("queue_persist", "failed to persist queue", {
      err: String(err),
      queue_size: inMemoryQueue.length,
    });
  }
}

function ensureQueueHydrated(): void {
  if (inMemoryQueue.length === 0 && isBrowser()) {
    inMemoryQueue = loadQueueFromStorage();
  }
}

function isOnline(): boolean {
  if (!isBrowser()) return true; // SSR では online とみなして fetch を試す
  if (typeof navigator === "undefined") return true;
  if (typeof navigator.onLine !== "boolean") return true;
  return navigator.onLine;
}

function makeQid(): string {
  // 軽量 uuid v4 風 (crypto.randomUUID 使えれば優先)
  if (
    isBrowser() &&
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `q-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 1 回だけ POST を試みる (retry 無し)。失敗は throw する。
 */
async function postOnce(input: LogUserActionInput): Promise<UserActionResponse> {
  return apiPost<UserActionResponse>("/api/users/actions", input);
}

/**
 * 指数バックオフで最大 MAX_RETRIES 回 retry する。
 * 全試行で失敗した場合 throw する。
 */
async function postWithRetry(
  input: LogUserActionInput,
  startingAttempt = 0,
): Promise<UserActionResponse> {
  let lastErr: unknown = null;
  for (let i = startingAttempt; i < MAX_RETRIES; i++) {
    try {
      return await postOnce(input);
    } catch (err) {
      lastErr = err;
      if (i < MAX_RETRIES - 1) {
        const delay = BASE_BACKOFF_MS * Math.pow(2, i);
        await sleep(delay);
      }
    }
  }
  throw lastErr ?? new Error("postWithRetry: unknown failure");
}

function enqueue(input: LogUserActionInput, attempts: number): void {
  ensureQueueHydrated();
  const entry: QueuedAction = {
    ...input,
    queued_at: Date.now(),
    attempts,
    qid: makeQid(),
  };
  inMemoryQueue.push(entry);
  persistQueue();
  installOnlineListener();
}

/**
 * queue に溜まった action を順次 flush する。
 * 1 件でも失敗すれば残りは queue に残し、後で再 flush する。
 */
async function flushQueue(): Promise<void> {
  if (flushScheduled) return;
  flushScheduled = true;
  try {
    ensureQueueHydrated();
    while (inMemoryQueue.length > 0) {
      if (!isOnline()) break;
      const head = inMemoryQueue[0];
      try {
        await postWithRetry(
          {
            action_type: head.action_type,
            target_type: head.target_type,
            target_id: head.target_id,
            context_json: head.context_json,
          },
          head.attempts,
        );
        // 成功 → queue から除去
        inMemoryQueue.shift();
        persistQueue();
      } catch (err) {
        // 失敗 → attempts++, それでも MAX_RETRIES 以上なら捨てる（structured log は残す）
        head.attempts = Math.min(MAX_RETRIES, head.attempts + 1);
        persistQueue();
        if (head.attempts >= MAX_RETRIES) {
          inMemoryQueue.shift();
          persistQueue();
          structuredError("queue_flush_drop", "dropping action after max retries", {
            qid: head.qid,
            action_type: head.action_type,
            err: String(err),
          });
        } else {
          // まだ retry 余地がある → 後で再試行するために break
          break;
        }
      }
    }
  } finally {
    flushScheduled = false;
  }
}

function installOnlineListener(): void {
  if (onlineListenerInstalled || !isBrowser()) return;
  onlineListenerInstalled = true;
  try {
    window.addEventListener("online", () => {
      void flushQueue();
    });
  } catch {
    // 何があっても UI を止めない
  }
}

/**
 * Log a user UI action to the backend.
 *
 * Behavior:
 *  - online: 指数バックオフ retry で POST。3 回失敗で queue に積み、後で flush。
 *  - offline: 直接 queue に積む。online 復帰時に flush。
 *  - SSR: apiPost を 1 回だけ試す。失敗時は swallow（queue は browser のみ）。
 *  - 例外は **絶対に throw しない**。UI を止めないため、戻り値 null で表現。
 */
export async function logUserAction(
  input: LogUserActionInput,
): Promise<UserActionResponse | null> {
  // SSR: queue を使わず一度だけ試して終わり
  if (!isBrowser()) {
    try {
      return await postOnce(input);
    } catch (err) {
      structuredError("ssr_post_failed", "logUserAction failed on SSR", {
        err: String(err),
        action_type: input.action_type,
      });
      return null;
    }
  }

  ensureQueueHydrated();
  installOnlineListener();

  // queue に既存の action がある場合は flush を先に試みる（順序保持）
  if (inMemoryQueue.length > 0 && isOnline()) {
    void flushQueue();
  }

  if (!isOnline()) {
    enqueue(input, 0);
    return null;
  }

  try {
    const result = await postWithRetry(input);
    return result;
  } catch (err) {
    structuredError("post_failed_enqueue", "POST failed, enqueueing for later", {
      err: String(err),
      action_type: input.action_type,
      target_type: input.target_type,
      target_id: input.target_id,
    });
    enqueue(input, MAX_RETRIES); // すでに retry 切れ → 後で flush 時に再試行はしないが、暫定で queue に残す
    return null;
  }
}

/**
 * Test / debug 用: 現在 queue を取得する。production の主機能では使わない。
 */
export function _getQueueSnapshot(): ReadonlyArray<QueuedAction> {
  ensureQueueHydrated();
  return [...inMemoryQueue];
}

/**
 * Test / debug 用: queue を強制 flush する。
 */
export async function _forceFlush(): Promise<void> {
  await flushQueue();
}
