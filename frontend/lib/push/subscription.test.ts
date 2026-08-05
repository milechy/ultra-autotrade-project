// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/lib/push/subscription.test.ts
//
// subscribeToPush / unsubscribeFromPush の unit test (2026-08-05)。
//
// これまで Playwright E2E のみでカバーしていたが、E2E は実サーバ + 認証済み
// セッションを要するため未認証環境では skip され、以下の分岐が実質未検証だった:
// - VAPID 未設定時に購読を作らないこと
// - サーバ登録失敗時にブラウザ側購読をロールバックすること (最重要)
// - ロールバック自体が失敗しても元の失敗を伝播すること
// - 解除はブラウザ先行 + サーバ側 best-effort であること
//
// 特に「サーバ登録失敗時のロールバック漏れ」は、ブラウザには購読があるのに
// サーバには無い = ユーザーは「通知ON」と思っているのに永久に届かない状態を作る
// (バックエンドの到達経路ゼロ障害と同型の乖離)。

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  PushSubscribeError,
  VapidNotConfiguredError,
  getExistingSubscription,
  isPushConfigured,
  subscribeToPush,
  unsubscribeFromPush,
} from "./subscription"

// 実際の VAPID 公開鍵と同じ形式 (65 バイトの非圧縮 EC 点 = base64url 87文字)。
// 長さが 4 の倍数 +1 になるような不正な base64 を使うと atob が
// InvalidCharacterError を投げ、テストしたい分岐に到達できない。
const VAPID_KEY =
  "BAcOFRwjKjE4P0ZNVFtiaXB3foWMk5qhqK-2vcTL0tng5-71_AMKERgfJi00O0JJUFdeZWxzeoGIj5adpKuyucA"

vi.mock("@/lib/api/http", () => ({
  postJson: vi.fn(),
  deleteJson: vi.fn(),
}))

import { deleteJson, postJson } from "@/lib/api/http"

type FakeSubscription = {
  endpoint: string
  toJSON: () => { endpoint: string; keys: { p256dh: string; auth: string } }
  unsubscribe: ReturnType<typeof vi.fn>
}

function makeFakeSubscription(endpoint = "https://fcm.googleapis.com/fcm/send/abc"): FakeSubscription {
  return {
    endpoint,
    toJSON: () => ({ endpoint, keys: { p256dh: "p256dh-value", auth: "auth-value" } }),
    unsubscribe: vi.fn().mockResolvedValue(true),
  }
}

/** navigator.serviceWorker.ready.pushManager をスタブする。 */
function stubServiceWorker(pushManager: Record<string, unknown>): void {
  Object.defineProperty(globalThis.navigator, "serviceWorker", {
    value: { ready: Promise.resolve({ pushManager }) },
    configurable: true,
    writable: true,
  })
}

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY

beforeEach(() => {
  process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY = VAPID_KEY
  vi.mocked(postJson).mockReset()
  vi.mocked(deleteJson).mockReset()
  vi.mocked(postJson).mockResolvedValue({} as never)
  vi.mocked(deleteJson).mockResolvedValue({} as never)
})

afterEach(() => {
  process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY = ORIGINAL_ENV
})

describe("isPushConfigured", () => {
  it("VAPID 公開鍵があれば true", () => {
    expect(isPushConfigured()).toBe(true)
  })

  it("VAPID 公開鍵が無ければ false (トグルを無効化するため)", () => {
    delete process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY
    expect(isPushConfigured()).toBe(false)
  })

  it("空文字も未設定として扱う", () => {
    process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY = ""
    expect(isPushConfigured()).toBe(false)
  })
})

describe("subscribeToPush", () => {
  it("正常系: 購読を作成しサーバへ endpoint と keys を送る", async () => {
    const sub = makeFakeSubscription()
    const subscribe = vi.fn().mockResolvedValue(sub)
    stubServiceWorker({ subscribe, getSubscription: vi.fn().mockResolvedValue(null) })

    await subscribeToPush("token-abc")

    expect(subscribe).toHaveBeenCalledOnce()
    // userVisibleOnly は Chrome で必須。落とすと subscribe が例外になる。
    expect(subscribe.mock.calls[0][0]).toMatchObject({ userVisibleOnly: true })

    expect(postJson).toHaveBeenCalledWith(
      "/notifications/push/subscribe",
      { endpoint: sub.endpoint, keys: { p256dh: "p256dh-value", auth: "auth-value" } },
      { headers: { Authorization: "Bearer token-abc" } }
    )
  })

  it("applicationServerKey は Uint8Array に変換して渡す", async () => {
    const subscribe = vi.fn().mockResolvedValue(makeFakeSubscription())
    stubServiceWorker({ subscribe, getSubscription: vi.fn() })

    await subscribeToPush("t")

    const key = subscribe.mock.calls[0][0].applicationServerKey
    expect(key).toBeInstanceOf(Uint8Array)
    expect((key as Uint8Array).byteLength).toBeGreaterThan(0)
  })

  it("VAPID 未設定なら VapidNotConfiguredError を投げ、購読を作らない", async () => {
    delete process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY
    const subscribe = vi.fn()
    stubServiceWorker({ subscribe, getSubscription: vi.fn() })

    await expect(subscribeToPush("t")).rejects.toThrow(VapidNotConfiguredError)
    expect(subscribe).not.toHaveBeenCalled()
    expect(postJson).not.toHaveBeenCalled()
  })

  it("サーバ登録が失敗したらブラウザ側購読をロールバックする (最重要)", async () => {
    const sub = makeFakeSubscription()
    stubServiceWorker({
      subscribe: vi.fn().mockResolvedValue(sub),
      getSubscription: vi.fn(),
    })
    vi.mocked(postJson).mockRejectedValue(new Error("500 Internal Server Error"))

    await expect(subscribeToPush("t")).rejects.toThrow(PushSubscribeError)
    expect(sub.unsubscribe).toHaveBeenCalledOnce()
  })

  it("ロールバックが失敗しても元のエラーを伝播する (成功と誤認させない)", async () => {
    const sub = makeFakeSubscription()
    sub.unsubscribe.mockRejectedValue(new Error("unsubscribe failed"))
    stubServiceWorker({ subscribe: vi.fn().mockResolvedValue(sub), getSubscription: vi.fn() })
    vi.mocked(postJson).mockRejectedValue(new Error("500"))

    await expect(subscribeToPush("t")).rejects.toThrow(PushSubscribeError)
  })

  it("サーバエラーのメッセージを PushSubscribeError に引き継ぐ", async () => {
    stubServiceWorker({
      subscribe: vi.fn().mockResolvedValue(makeFakeSubscription()),
      getSubscription: vi.fn(),
    })
    vi.mocked(postJson).mockRejectedValue(new Error("422 invalid keys"))

    await expect(subscribeToPush("t")).rejects.toThrow(/422 invalid keys/)
  })

  it("pushManager.subscribe 自体が失敗した場合はサーバへ送らない", async () => {
    stubServiceWorker({
      subscribe: vi.fn().mockRejectedValue(new Error("permission denied")),
      getSubscription: vi.fn(),
    })

    await expect(subscribeToPush("t")).rejects.toThrow()
    expect(postJson).not.toHaveBeenCalled()
  })
})

describe("unsubscribeFromPush", () => {
  it("購読が無ければ何もしない (冪等)", async () => {
    stubServiceWorker({ getSubscription: vi.fn().mockResolvedValue(null), subscribe: vi.fn() })

    await unsubscribeFromPush("t")

    expect(deleteJson).not.toHaveBeenCalled()
  })

  it("ブラウザ側を解除し、サーバへ endpoint を URL エンコードして通知する", async () => {
    const sub = makeFakeSubscription("https://fcm.googleapis.com/fcm/send/a+b/c?d=1")
    stubServiceWorker({ getSubscription: vi.fn().mockResolvedValue(sub), subscribe: vi.fn() })

    await unsubscribeFromPush("token-xyz")

    expect(sub.unsubscribe).toHaveBeenCalledOnce()
    const calledUrl = vi.mocked(deleteJson).mock.calls[0][0] as string
    expect(calledUrl).toContain(encodeURIComponent(sub.endpoint))
    // 生の endpoint がそのまま連結されるとクエリ境界が壊れる。
    expect(calledUrl).not.toContain("send/a+b/c?d=1")
    expect(vi.mocked(deleteJson).mock.calls[0][1]).toEqual({
      headers: { Authorization: "Bearer token-xyz" },
    })
  })

  it("サーバ側解除の失敗は投げない (ブラウザ側は既に解除済み・fail-open)", async () => {
    const sub = makeFakeSubscription()
    stubServiceWorker({ getSubscription: vi.fn().mockResolvedValue(sub), subscribe: vi.fn() })
    vi.mocked(deleteJson).mockRejectedValue(new Error("network down"))

    await expect(unsubscribeFromPush("t")).resolves.toBeUndefined()
    expect(sub.unsubscribe).toHaveBeenCalledOnce()
  })

  it("ブラウザ側解除より先にサーバへ送らない (順序: browser → server)", async () => {
    const order: string[] = []
    const sub = makeFakeSubscription()
    sub.unsubscribe.mockImplementation(async () => {
      order.push("browser")
      return true
    })
    vi.mocked(deleteJson).mockImplementation(async () => {
      order.push("server")
      return {} as never
    })
    stubServiceWorker({ getSubscription: vi.fn().mockResolvedValue(sub), subscribe: vi.fn() })

    await unsubscribeFromPush("t")

    expect(order).toEqual(["browser", "server"])
  })
})

describe("getExistingSubscription", () => {
  it("Service Worker 非対応環境では null (例外を投げない)", async () => {
    // @ts-expect-error - 非対応環境を再現するため意図的に削除する
    delete globalThis.navigator.serviceWorker

    await expect(getExistingSubscription()).resolves.toBeNull()
  })

  it("既存購読があればそれを返す", async () => {
    const sub = makeFakeSubscription()
    stubServiceWorker({ getSubscription: vi.fn().mockResolvedValue(sub), subscribe: vi.fn() })

    await expect(getExistingSubscription()).resolves.toBe(sub)
  })
})
