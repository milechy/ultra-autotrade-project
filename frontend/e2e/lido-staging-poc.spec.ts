// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [Phase A-2] Lido PoC staging 実機検証 E2E
//
// 目的: staging-new の Lido エンドポイント 4 本 + health を HTTP レベルで検証
// 認証: CF Access Service Token (Bearer トークン不要 / 内部 API)
//
// 実行前提条件 (Gate 4 実行可能条件):
//   1. P0-1 fix (Asana GID 1214821930631284): DummyLidoClient 本番ガード
//      /api/protocols/lido/status が 503 ではなく 200 を返すこと
//   2. SSH 鍵: ssh-add ~/.ssh/hetzner_staging で agent にロード済み
//   3. 環境変数: CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET 設定済み
//
// 現在の状態 (2026-05-15):
//   staging lido health = 500 → Gate 4 は P0-1 fix 後 (明日朝 Opus セッション) に実施
//
// 実行方法 (P0-1 fix 後):
//   CF_ACCESS_CLIENT_ID=xxx CF_ACCESS_CLIENT_SECRET=yyy \
//   npx playwright test e2e/lido-staging-poc.spec.ts

import { test, expect, APIRequestContext } from '@playwright/test'

const STAGING_API = process.env.STAGING_API_URL ?? 'http://localhost:8082'

// CF Access Service Token (staging は CF Access 保護下)
const CF_CLIENT_ID = process.env.CF_ACCESS_CLIENT_ID ?? ''
const CF_CLIENT_SECRET = process.env.CF_ACCESS_CLIENT_SECRET ?? ''
const CF_HEADERS: Record<string, string> =
  CF_CLIENT_ID && CF_CLIENT_SECRET
    ? {
        'CF-Access-Client-Id': CF_CLIENT_ID,
        'CF-Access-Client-Secret': CF_CLIENT_SECRET,
      }
    : {}

// Gate 4 保留: P0-1 (DummyLidoClient guard) fix が完了するまでスキップ
const STAGING_GATE4_READY = process.env.STAGING_GATE4_READY === 'true'

test.describe('[Phase A-2] Lido PoC — staging 実機検証', () => {
  test.use({ extraHTTPHeaders: CF_HEADERS })

  // -----------------------------------------------------------------------
  // GET /api/protocols/lido/status
  // -----------------------------------------------------------------------
  test('GET /api/protocols/lido/status → 200 + 必須フィールド', async ({ request }) => {
    test.skip(!STAGING_GATE4_READY, 'P0-1 fix (GID 1214821930631284) 待ち — STAGING_GATE4_READY=true で解除')

    const res = await request.get(`${STAGING_API}/api/protocols/lido/status`)
    expect(res.status()).toBe(200)

    const data = await res.json()
    expect(data).toHaveProperty('steth_balance')
    expect(data).toHaveProperty('staking_apr')
    expect(data).toHaveProperty('steth_eth_ratio')
    expect(data).toHaveProperty('peg_deviation_pct')
    expect(data).toHaveProperty('chain')
    expect(data).toHaveProperty('sandbox')

    // staging は sandbox モード
    expect(data.sandbox).toBe(true)
    // Decimal 値が文字列で返ること (float 禁止)
    expect(typeof data.staking_apr).not.toBe('number')
  })

  // -----------------------------------------------------------------------
  // GET /api/protocols/lido/apr
  // -----------------------------------------------------------------------
  test('GET /api/protocols/lido/apr → 200 + APR フィールド', async ({ request }) => {
    test.skip(!STAGING_GATE4_READY, 'P0-1 fix 待ち — STAGING_GATE4_READY=true で解除')

    const res = await request.get(`${STAGING_API}/api/protocols/lido/apr`)
    expect(res.status()).toBe(200)

    const data = await res.json()
    expect(data).toHaveProperty('staking_apr')
    expect(data).toHaveProperty('source')
    expect(typeof data.staking_apr).not.toBe('number')
  })

  // -----------------------------------------------------------------------
  // POST /api/protocols/lido/stake (dry_run)
  // -----------------------------------------------------------------------
  test('POST /api/protocols/lido/stake dry_run → 200 + dry_run=true', async ({ request }) => {
    test.skip(!STAGING_GATE4_READY, 'P0-1 fix 待ち — STAGING_GATE4_READY=true で解除')

    const res = await request.post(`${STAGING_API}/api/protocols/lido/stake`, {
      data: { amount_eth: '0.01', dry_run: true },
    })
    expect(res.status()).toBe(200)

    const data = await res.json()
    expect(data.dry_run).toBe(true)
    expect(data.tx_hash).toBeNull()
    expect(data.operation).toBe('STAKE')
  })

  // -----------------------------------------------------------------------
  // POST /api/protocols/lido/withdraw (dry_run)
  // -----------------------------------------------------------------------
  test('POST /api/protocols/lido/withdraw dry_run → 200 + WITHDRAW_REQUEST', async ({ request }) => {
    test.skip(!STAGING_GATE4_READY, 'P0-1 fix 待ち — STAGING_GATE4_READY=true で解除')

    const res = await request.post(`${STAGING_API}/api/protocols/lido/withdraw`, {
      data: { amount_steth: '0.01', dry_run: true },
    })
    expect(res.status()).toBe(200)

    const data = await res.json()
    expect(data.dry_run).toBe(true)
    expect(data.tx_hash).toBeNull()
    expect(data.operation).toBe('WITHDRAW_REQUEST')
    expect(data.note).toBeTruthy()
  })

  // -----------------------------------------------------------------------
  // GET /api/protocols/health/lido (Protocol Health Monitor)
  // -----------------------------------------------------------------------
  test('GET /api/protocols/health/lido → 200 + ProtocolHealth フィールド', async ({ request }) => {
    test.skip(!STAGING_GATE4_READY, 'P0-1 fix 待ち — STAGING_GATE4_READY=true で解除')

    const res = await request.get(`${STAGING_API}/api/protocols/health/lido`)
    expect(res.status()).toBe(200)

    const data = await res.json()
    expect(data).toHaveProperty('protocol')
    expect(data).toHaveProperty('is_operational')
    expect(data).toHaveProperty('risk_level')
    expect(data.protocol).toBe('lido')
  })

  // -----------------------------------------------------------------------
  // Sanity check (常時実行可能 — Gate 4 保留関係なし)
  // -----------------------------------------------------------------------
  test('[sanity] staging backend が応答すること', async ({ request }) => {
    // Playwright は接続不可時に例外を throw するため try-catch で処理
    let status: number
    try {
      const res = await request.get(`${STAGING_API}/health`)
      status = res.status()
    } catch {
      test.skip(true, 'staging backend 到達不可 — SSH / CF Access 設定を確認')
      return
    }
    expect(status).toBeLessThan(500)
  })
})
