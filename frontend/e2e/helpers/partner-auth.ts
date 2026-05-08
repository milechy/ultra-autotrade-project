// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Shared partner auth setup helper.
// Extracted from partner-wallet-link.spec.ts / yamamoto-partner-flow.spec.ts
// to avoid duplication across RAS specs.

import type { Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'

export const PARTNER_MOCK_USER = {
  id: 15,
  email: 'e2e-user@ultra-autotrade.com',
  username: 'e2e-user',
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

/** e2e/.auth/partner.json から JWT を読む。ファイルがなければ undefined。 */
export function readPartnerAuth(): { token: string; expiresAt: number } | undefined {
  const authPath = path.join('e2e', '.auth', 'partner.json')
  if (!fs.existsSync(authPath)) return undefined
  return JSON.parse(fs.readFileSync(authPath, 'utf-8')) as {
    token: string
    expiresAt: number
    email?: string
  }
}

/**
 * partner JWT を localStorage に注入 + GET /auth/me をモック。
 * PartnerGuard が /login にリダイレクトしないための最小セットアップ。
 * page.goto() の前に呼ぶこと。
 */
export async function setupPartnerAuth(page: Page): Promise<void> {
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
