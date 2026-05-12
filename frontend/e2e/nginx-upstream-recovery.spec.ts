// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// nginx upstream IP 固着リカバリ検証 (2026-05-12 P0 hotfix)
//
// 背景:
//   2026-05-12 12:00 production で `deploy_production.sh --frontend-only` 実行直後から
//   nginx → backend の upstream で 502 を 3h+ 継続。真因は nginx.conf に resolver 未設定で、
//   upstream block 内の `server backend-blue:8000` hostname が起動時 1 回しか解決されず、
//   backend container 再生成で IP 変動した際に古い IP に固着した。
//
//   恒久対策として:
//   - nginx.conf に `resolver 127.0.0.11 valid=5s ipv6=off;` 追加
//   - upstream.{production,staging}.conf を `set $backend backend-blue:8000;` に変更
//   - `proxy_pass http://$backend;` の変数経由で TTL 5s 動的解決
//
// 本テストの目的:
//   nginx 経由の /health が常に 200 で、5s+ の窓で連続成功することを担保する。
//   backend recreate 等で IP 変動した場合の自動復旧も将来 chaos test で検証。
//
// 実行:
//   - production 外形検証 (デフォルト): npx playwright test e2e/nginx-upstream-recovery.spec.ts
//   - staging 外形検証: HEALTH_URL=https://api-staging.ultra-auto-trade.com/health \
//     CF_ACCESS_CLIENT_ID=... CF_ACCESS_CLIENT_SECRET=... \
//     npx playwright test e2e/nginx-upstream-recovery.spec.ts
//
// 認証: 不要 (公開 /health エンドポイント、CF Access が付いている staging は Service Token で透過)

import { test, expect, request as pwRequest } from '@playwright/test'

const HEALTH_URL =
  process.env.HEALTH_URL ?? 'https://api.ultra-auto-trade.com/health'
const CF_ACCESS_CLIENT_ID = process.env.CF_ACCESS_CLIENT_ID
const CF_ACCESS_CLIENT_SECRET = process.env.CF_ACCESS_CLIENT_SECRET

test.describe('nginx upstream リカバリ (2026-05-12 P0)', () => {
  // CF Access Service Token が指定された場合のみヘッダを付与 (staging で必要なケースに備える)。
  // /health 自体は CF Access 保護外でも 200 を返す現行構成のため、トークン未指定でも実行可能。
  const extraHeaders: Record<string, string> = {}
  if (CF_ACCESS_CLIENT_ID && CF_ACCESS_CLIENT_SECRET) {
    extraHeaders['CF-Access-Client-Id'] = CF_ACCESS_CLIENT_ID
    extraHeaders['CF-Access-Client-Secret'] = CF_ACCESS_CLIENT_SECRET
  }

  test(`/health 5 回連続 200 (${HEALTH_URL})`, async () => {
    const ctx = await pwRequest.newContext({ extraHTTPHeaders: extraHeaders })

    const results: number[] = []
    for (let i = 0; i < 5; i += 1) {
      const res = await ctx.get(HEALTH_URL, { timeout: 8_000 })
      results.push(res.status())
      // 連続性を見るために 2 秒ずつ間隔をあける
      // (DNS TTL 5s より短い間隔で多重解決が発生しないことを確認)
      if (i < 4) await new Promise((r) => setTimeout(r, 2_000))
    }

    await ctx.dispose()

    // 5 回全てが 200 でなければ 502 残留疑い
    expect(
      results,
      `nginx upstream リカバリ失敗の疑い (502 続発): results=${JSON.stringify(results)}`,
    ).toEqual([200, 200, 200, 200, 200])
  })

  test(`/health body に scheduler_healthy / status フィールドが返る`, async () => {
    const ctx = await pwRequest.newContext({ extraHTTPHeaders: extraHeaders })

    const res = await ctx.get(HEALTH_URL, { timeout: 8_000 })
    expect(res.status()).toBe(200)

    const body = await res.json()
    // backend が本当に応答しているか (nginx の固定レスポンスで誤魔化されていないか) を担保
    expect(body).toHaveProperty('status')
    // scheduler_healthy は backend FastAPI の /health が返す本物のフィールド
    expect(body).toHaveProperty('scheduler_healthy')

    await ctx.dispose()
  })
})
