// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Playwright global setup: log in once and cache the JWT for all tests.
// Prevents rate-limit hits (5/min) when 24+ tests each call /auth/login.
//
// Outputs (when credentials are set):
//   e2e/.auth/partner.json       { token, expiresAt, email }       (legacy)
//   e2e/.auth/storageState.json  Playwright standard storageState  (new)
//
// Credentials 未設定時 (E2E_PARTNER_EMAIL or E2E_PARTNER_PASSWORD 不在):
//   - 警告 log を出すだけで partner.json / storageState.json は **書かない**
//   - process.env.E2E_AUTH_SKIPPED='1' を set
//     (各 spec / launch_gate L3 がこの flag で graceful skip 判定する)
//   - throw しない (= playwright が global-setup 失敗で全件 fail にしない)
//
// この方針により、credentials なしでの実行は「全 skip」となり、L3_e2e.sh
// 側の「NO TESTS RAN — SKIP ONLY」検出に乗って **FAIL** として扱われる。
// (§7 verify.sh 罠 — "skip だけで緑" を作らない)

import fs from 'fs'
import path from 'path'

export default async function globalSetup(): Promise<void> {
  const email = process.env.E2E_PARTNER_EMAIL
  const password = process.env.E2E_PARTNER_PASSWORD

  if (!email || !password) {
    // credentials 未設定: graceful skip。各 spec が test.skip() で個別判定する。
    process.env.E2E_AUTH_SKIPPED = '1'
    console.warn(
      '[global-setup] E2E_PARTNER_EMAIL / E2E_PARTNER_PASSWORD が未設定です。',
    )
    console.warn(
      '[global-setup] auth cache を作成しません — 認証必須テストは個別に skip されます。',
    )
    console.warn(
      '[global-setup] launch_gate L3 はこの状況を "NO TESTS RAN" として FAIL 扱いします。',
    )
    return
  }

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? 'https://api.ultra-auto-trade.com'

  const cfHeaders: Record<string, string> =
    process.env.CF_ACCESS_CLIENT_ID && process.env.CF_ACCESS_CLIENT_SECRET
      ? {
          'CF-Access-Client-Id': process.env.CF_ACCESS_CLIENT_ID,
          'CF-Access-Client-Secret': process.env.CF_ACCESS_CLIENT_SECRET,
        }
      : {}

  let res: Response
  try {
    res = await fetch(`${backendUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...cfHeaders },
      body: JSON.stringify({ email, password }),
    })
  } catch (e) {
    // ネットワーク失敗時も throw せず graceful skip
    process.env.E2E_AUTH_SKIPPED = '1'
    console.warn(`[global-setup] /auth/login 接続失敗: ${(e as Error).message}`)
    console.warn('[global-setup] auth cache を作成しません — 全テスト個別 skip')
    return
  }

  if (!res.ok) {
    process.env.E2E_AUTH_SKIPPED = '1'
    console.warn(
      `[global-setup] /auth/login failed: ${res.status} — auth cache を作成しません`,
    )
    return
  }

  const data = (await res.json()) as { access_token: string; expires_in: number }
  const expiresAt = Date.now() + data.expires_in * 1000

  const authDir = path.join(process.cwd(), 'e2e', '.auth')
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true })

  // 互換維持: 既存 spec が読む JWT cache 構造はそのまま残す
  fs.writeFileSync(
    path.join(authDir, 'partner.json'),
    JSON.stringify({ token: data.access_token, expiresAt, email }),
  )

  // 新規: Playwright 標準形式の storageState.json も書き出す。
  //       baseURL の host から推定した localStorage entry を投入する。
  //       (yamamoto-partner-flow.spec.ts は現状 addInitScript で localStorage
  //        を注入しているため、storageState は補助的位置づけ)
  try {
    const baseUrl = process.env.STAGING_URL || 'https://app.ultra-auto-trade.com'
    const origin = new URL(baseUrl).origin
    const storageState = {
      cookies: [] as unknown[],
      origins: [
        {
          origin,
          localStorage: [
            { name: 'ultra_auth_token', value: data.access_token },
            { name: 'ultra_auth_expires', value: String(expiresAt) },
          ],
        },
      ],
    }
    fs.writeFileSync(
      path.join(authDir, 'storageState.json'),
      JSON.stringify(storageState),
    )
  } catch (e) {
    console.warn(
      `[global-setup] storageState.json 書き出しに失敗 (致命的ではない): ${(e as Error).message}`,
    )
  }

  console.log('[global-setup] Partner auth state cached (partner.json + storageState.json)')
}
