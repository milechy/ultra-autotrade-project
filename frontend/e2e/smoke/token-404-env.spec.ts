// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [gate] token / 404 / env-isolation — 実 staging backend 必須 gate
//
// e2e-smoke の必須 gate はこの 3 系統のみ。
// page.route / route.fulfill などの mock は一切使わない。
// global-setup が /auth/login で取得した実 JWT を直接使い、
// 実 staging backend を Node.js fetch で叩く。
//
// CI mock-backend 環境 (e2e-smoke ジョブ / continue-on-error: true) での動作:
//   - 認証情報 (E2E_PARTNER_EMAIL / E2E_PARTNER_PASSWORD) 未設定
//     → global-setup が E2E_AUTH_SKIPPED=1 を set
//     → test.beforeEach で全テストが graceful skip
//     → Playwright exit 0 (failures なし) — 既存 e2e-smoke の挙動を壊さない
//
// e2e-smoke-gate ジョブ (必須 gate / §7 三重防止) での動作:
//   (1) pre-flight step: credentials / backend URL 未設定 → exit 1 → job FAIL
//       (skip-green 禁止。初回 merge 直後は secrets 突合まで赤が正常)
//   (2) global-setup が /auth/login → JWT 取得 → e2e/.auth/partner.json 書き出し
//   (3) 3 テスト実行 → 全 pass で gate 通過
//   (4) post-run verify (if:always): 0 passed (NO TESTS RAN) → exit 1 → job FAIL
//       (global-setup が auth 失敗し E2E_AUTH_SKIPPED=1 を set したケースを捕捉)
//
// 実行方法:
//   # 実 staging backend (credentials 必要)
//   NEXT_PUBLIC_BACKEND_BASE_URL=https://api-staging.ultra-auto-trade.com \
//   STAGING_URL=https://app-staging.ultra-auto-trade.com \
//   E2E_PARTNER_EMAIL=xxx E2E_PARTNER_PASSWORD=xxx \
//   npx playwright test e2e/smoke/token-404-env.spec.ts
//
//   # CI mock-backend 環境 (全 skip になる)
//   npx playwright test e2e/smoke/token-404-env.spec.ts

import { test, expect } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? ''

const CF_HEADERS: Record<string, string> =
  process.env.CF_ACCESS_CLIENT_ID && process.env.CF_ACCESS_CLIENT_SECRET
    ? {
        'CF-Access-Client-Id': process.env.CF_ACCESS_CLIENT_ID,
        'CF-Access-Client-Secret': process.env.CF_ACCESS_CLIENT_SECRET,
      }
    : {}

function readPartnerAuth(): { token: string; email: string } | null {
  const authFile = path.join(process.cwd(), 'e2e', '.auth', 'partner.json')
  if (!fs.existsSync(authFile)) return null
  try {
    return JSON.parse(fs.readFileSync(authFile, 'utf-8')) as {
      token: string
      email: string
    }
  } catch {
    return null
  }
}

test.describe('[gate] token / 404 / env-isolation — real staging backend', () => {
  // CI の mock-backend 環境では global-setup が E2E_AUTH_SKIPPED=1 を set するため全 skip
  test.beforeEach(() => {
    test.skip(
      process.env.E2E_AUTH_SKIPPED === '1',
      'E2E_AUTH_SKIPPED=1: 認証情報未設定 (CI mock-backend 環境) → graceful skip',
    )
    test.skip(
      !BACKEND_URL,
      'NEXT_PUBLIC_BACKEND_BASE_URL 未設定 → 実 backend を特定できないため skip',
    )
  })

  // ──────────────────────────────────────────────────────────────────────────
  // T-1: token gate
  //   global-setup が /auth/login で取得した実 JWT を使い、
  //   実 /auth/me を呼んで 200 が返ることを確認する。
  //   200 が返れば JWT が有効かつ backend が生きていることを同時に証明する。
  //   page.route mock なし — ネットワーク直通。
  // ──────────────────────────────────────────────────────────────────────────
  test('[token] GET /auth/me が実 JWT で 200 を返す', async () => {
    const auth = readPartnerAuth()
    test.skip(!auth, 'e2e/.auth/partner.json 未生成 — global-setup が未実行')

    const res = await fetch(`${BACKEND_URL}/auth/me`, {
      headers: {
        Authorization: `Bearer ${auth!.token}`,
        ...CF_HEADERS,
      },
    })

    expect(
      res.status,
      `GET ${BACKEND_URL}/auth/me → 200 を期待 (失敗なら JWT 無効か backend 未起動)`,
    ).toBe(200)

    const body = (await res.json()) as { email?: string; role?: string }
    expect(body.email, '/auth/me レスポンスに email が含まれること').toBeTruthy()
    expect(body.role, '/auth/me レスポンスに role が含まれること').toBeTruthy()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // T-2: 404 gate
  //   実 backend の存在しないパスが 404 を返すことを確認する。
  //   CI の mock backend は全パスに 200 を返す設計なので、
  //   このテストが pass = 実 backend を叩けている証拠にもなる。
  //   page.route mock なし — ネットワーク直通。
  // ──────────────────────────────────────────────────────────────────────────
  test('[404] 存在しないパスが実 backend から 404 を返す', async () => {
    const res = await fetch(
      `${BACKEND_URL}/nonexistent-smoke-gate-xyzzy-12345`,
      { headers: CF_HEADERS },
    )

    expect(
      res.status,
      `GET ${BACKEND_URL}/nonexistent-smoke-gate-xyzzy-12345 → 404 を期待 ` +
        '(200 が返れば mock backend を叩いている疑い)',
    ).toBe(404)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // T-3: env-isolation gate
  //   staging 実行中に NEXT_PUBLIC_BACKEND_BASE_URL が
  //   production URL (api.ultra-auto-trade.com) を向いていないことを確認する。
  //   staging frontend が誤って production backend を叩く env drift を検出する。
  //   (ドリフト再発カタログ: CLAUDE.md §ドリフト再発カタログ 参照)
  //   page.route mock なし — env var と /health への実リクエストで判定。
  // ──────────────────────────────────────────────────────────────────────────
  test('[env-isolation] staging 実行時に BACKEND_URL が production を向かない', async () => {
    const stagingUrl = process.env.STAGING_URL ?? ''

    // STAGING_URL が staging / localhost を含む場合のみ env 分離を強制検証
    const isKnownStagingRun =
      stagingUrl.includes('staging') || stagingUrl.includes('localhost')
    test.skip(
      !isKnownStagingRun,
      `STAGING_URL="${stagingUrl}" から staging 実行を判定できないため skip`,
    )

    // production URL と完全一致しない
    expect(
      BACKEND_URL,
      'staging 実行時: NEXT_PUBLIC_BACKEND_BASE_URL が production URL であってはならない',
    ).not.toBe('https://api.ultra-auto-trade.com')

    // production ドメインを含まない
    expect(
      BACKEND_URL,
      'staging 実行時: NEXT_PUBLIC_BACKEND_BASE_URL に api.ultra-auto-trade.com が含まれていてはならない',
    ).not.toContain('api.ultra-auto-trade.com')

    // 設定された backend URL が実際に /health で応答する
    const res = await fetch(`${BACKEND_URL}/health`, { headers: CF_HEADERS })
    expect(
      res.status,
      `GET ${BACKEND_URL}/health → 500 未満を期待`,
    ).toBeLessThan(500)
  })
})
