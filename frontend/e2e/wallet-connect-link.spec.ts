// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [2026-05-12 hotfix] WalletConnectCard 実署名フロー E2E
//
// 背景: 5/12 P0 hotfix で /partner/settings の WalletConnectCard が
// 「空 POST → 200 確認」から「Privy modal → 実署名 → POST {address,signature,message}」
// へ変更された (前実装は実装抜けで本番で動かなかった: 策 18)。
//
// 検証範囲:
//   (UI) TC-A: 未接続 UI が表示される
//   (UI) TC-B: ボタン押下時に Privy login() が呼ばれる (Privy 接続前は POST が発火しない)
//   (Backend integration) TC-G6: viem 実署名で POST /auth/wallet/link 200 → DB 反映
//
// staging-new での実行を想定 (NEXT_PUBLIC_BACKEND_BASE_URL=https://api.ultra-auto-trade.com)。
// partner.json (E2E_PARTNER_EMAIL/PASSWORD で生成) が前提。

import { test, expect, Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { signWalletLinkPayload, getTestAccount } from './fixtures/privy'

const PARTNER_MOCK_USER = {
  id: 15,
  email: 'partner-e2e@ultra-autotrade.com',
  username: 'partner-e2e',
  role: 'partner',
  is_active: true,
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
  terms_accepted_at: null,
  terms_version: null,
  risk_mode: 'conservative',
  invited_by: null,
  tier: 'GENERAL',
  risk_mode_label: 'ローリスク',
}

function readPartnerAuth(): { token: string; expiresAt: number } | undefined {
  const authPath = path.join('e2e', '.auth', 'partner.json')
  if (!fs.existsSync(authPath)) return undefined
  return JSON.parse(fs.readFileSync(authPath, 'utf-8'))
}

async function setupPartnerAuth(page: Page): Promise<void> {
  const auth = readPartnerAuth()
  const token = auth?.token ?? 'dummy-partner-token-for-e2e'
  const safeExpiresAt = Math.max(
    auth?.expiresAt ?? 0,
    Date.now() + 24 * 60 * 60 * 1000,
  )

  await page.addInitScript(
    (args) => {
      localStorage.setItem(args.tokenKey, args.t)
      localStorage.setItem(args.expiresKey, String(args.e))
    },
    {
      tokenKey: 'ultra_auth_token',
      expiresKey: 'ultra_auth_expires',
      t: token,
      e: safeExpiresAt,
    },
  )

  await page.route('**/auth/me', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(PARTNER_MOCK_USER),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/api/user/settings', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user_mode: 'managed', execution_policy: 'conservative' }),
      })
    } else {
      await route.continue()
    }
  })
}

// ─── UI Layer ────────────────────────────────────────────────────────────────

test.describe('[wallet-link UI] WalletConnectCard sign flow', () => {
  test('TC-A: /partner/settings に未接続 UI と「ウォレット接続」ボタンが表示される', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await page.goto('/partner/settings')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByText('ウォレット未接続')).toBeVisible({ timeout: 10_000 })
    await expect(
      page.getByRole('button', { name: 'ウォレット接続' }),
    ).toBeVisible()
  })

  test('TC-B: Privy 未接続時にボタンを押すと /auth/wallet/link への POST は発火しない (login() ルート)', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    let linkPostFired = false
    await page.route('**/auth/wallet/link', async (route) => {
      if (route.request().method() === 'POST') {
        linkPostFired = true
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user_id: 15,
            wallet_address: '0x0000000000000000000000000000000000000000',
            linked_at: '2026-05-12T00:00:00+00:00',
          }),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/settings')
    await page.waitForLoadState('domcontentloaded')

    const btn = page.getByRole('button', { name: 'ウォレット接続' })
    await expect(btn).toBeVisible({ timeout: 10_000 })
    await btn.click()

    // Privy modal を待ち、その間に POST が発火していないこと
    await page.waitForTimeout(1_500)
    expect(linkPostFired).toBe(false)
    // 「接続済み:」UI に切り替わっていないこと
    await expect(page.getByText('接続済み:')).not.toBeVisible()
  })
})

// ─── Backend integration ─────────────────────────────────────────────────────

test.describe('[wallet-link backend] /auth/wallet/link 200 path with viem signature', () => {
  test('TC-G6: viem 実署名 → POST 200 + GET /auth/me.wallet_address 反映 (idempotent)', async ({
    request,
  }) => {
    const auth = readPartnerAuth()
    test.skip(!auth, 'partner.json なし — E2E_PARTNER_EMAIL / PASSWORD を設定して再実行')

    const backendUrl =
      process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? 'https://api.ultra-auto-trade.com'

    const payload = await signWalletLinkPayload()
    const expectedAddress = getTestAccount().address.toLowerCase()

    const linkResp = await request.post(`${backendUrl}/auth/wallet/link`, {
      headers: {
        Authorization: `Bearer ${auth!.token}`,
        'Content-Type': 'application/json',
      },
      data: payload,
    })

    if (linkResp.status() === 409) {
      throw new Error(
        `409: ${expectedAddress} が partner test user 以外にリンク済。` +
          'staging-new で UPDATE users SET wallet_address=NULL WHERE id != <partner_id> を実行のこと。',
      )
    }
    expect(linkResp.status(), `link response: ${await linkResp.text()}`).toBe(200)

    const linkBody = (await linkResp.json()) as {
      user_id: number
      wallet_address: string
      linked_at: string
    }
    expect(linkBody.wallet_address).toBe(expectedAddress)
    expect(linkBody.linked_at).toMatch(/T.*\d/)

    const meResp = await request.get(`${backendUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${auth!.token}` },
    })
    expect(meResp.status()).toBe(200)
    const meBody = (await meResp.json()) as { wallet_address?: string | null }
    expect(meBody.wallet_address).toBe(expectedAddress)
  })
})
