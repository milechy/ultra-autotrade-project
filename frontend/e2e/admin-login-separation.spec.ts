// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Asana 1214162094588652: 管理者 /admin/login 分離 E2E
//
// 目的:
//   - /admin/login が独立した管理者専用ログインページとして機能すること
//   - /admin/* (e.g. /dashboard) アクセス時に未認証なら /admin/login にリダイレクトされること
//   - 不正な credential で 401 + エラー表示
//   - 管理者 credential で /dashboard にリダイレクトされること (任意、E2E_ADMIN_* 設定時のみ)
//   - 一般ユーザー (partner/viewer) credential では /dashboard にアクセスできないこと
//   - /login に「管理者の方はこちら」リンクが存在し /admin/login に飛ぶこと
//
// 実行方法:
//   # 本番向け (デフォルト)
//   npx playwright test e2e/admin-login-separation.spec.ts
//
//   # staging 向け
//   STAGING_URL=https://staging.ultra-auto-trade.com \
//   npx playwright test e2e/admin-login-separation.spec.ts
//
// 認証: ベースのテストは未認証で動作する。フル認証フローは
//   E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD が設定されている場合のみ実行。

import { test, expect } from '@playwright/test'

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD
const PARTNER_EMAIL = process.env.E2E_PARTNER_EMAIL
const PARTNER_PASSWORD = process.env.E2E_PARTNER_PASSWORD

test.describe('/admin/login — ページ表示と基本構造', () => {
  test('/admin/login が 200 で読み込める', async ({ page }) => {
    const response = await page.goto('/admin/login')
    expect(response?.status()).toBe(200)
  })

  test('/admin/login に email/password フォームが表示される', async ({ page }) => {
    await page.goto('/admin/login')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByTestId('admin-login-card')).toBeVisible()
    await expect(page.getByTestId('admin-login-email')).toBeVisible()
    await expect(page.getByTestId('admin-login-password')).toBeVisible()
    await expect(page.getByTestId('admin-login-submit')).toBeVisible()
  })

  test('/admin/login にタイトル「管理者ログイン」が表示される', async ({ page }) => {
    await page.goto('/admin/login')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByText('管理者ログイン').first()).toBeVisible()
  })
})

test.describe('/admin/login — エラー処理', () => {
  test('不正な credential でエラーメッセージが表示される', async ({ page }) => {
    await page.goto('/admin/login')
    await page.waitForLoadState('domcontentloaded')

    await page.getByTestId('admin-login-email').fill('not-a-real-user@example.invalid')
    await page.getByTestId('admin-login-password').fill('definitely-wrong-password')
    await page.getByTestId('admin-login-submit').click()

    // エラー表示は最大 10s 待つ (バックエンド rate limit / network 起因の遅延を許容)
    await expect(page.getByTestId('admin-login-error')).toBeVisible({ timeout: 10_000 })
  })
})

test.describe('/admin/* — 未認証ロール check', () => {
  test('未認証で /dashboard にアクセスすると /admin/login へリダイレクトされる', async ({ page }) => {
    // localStorage を確実にクリアして未認証状態を作る
    await page.goto('/admin/login')
    await page.evaluate(() => {
      localStorage.removeItem('ultra_auth_token')
      localStorage.removeItem('ultra_auth_expires')
    })

    await page.goto('/dashboard')
    await page.waitForLoadState('domcontentloaded')

    // AdminGuard の useEffect は client-side リダイレクトのため少し待つ
    await page.waitForURL(/\/admin\/login/, { timeout: 10_000 }).catch(() => {})

    expect(page.url()).toContain('/admin/login')
  })
})

test.describe('/login — 管理者の方はこちらリンク', () => {
  test('/login に「管理者の方はこちら」リンクが存在する', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    const adminLink = page.getByTestId('login-admin-link')
    await expect(adminLink).toBeVisible()
    await expect(adminLink).toHaveText(/管理者の方はこちら/)
  })

  test('「管理者の方はこちら」リンクが /admin/login に飛ぶ', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    await page.getByTestId('login-admin-link').click()
    await page.waitForURL(/\/admin\/login/, { timeout: 10_000 })

    expect(page.url()).toContain('/admin/login')
    await expect(page.getByTestId('admin-login-card')).toBeVisible()
  })
})

// ----------------------------------------------------------------
// 認証フローテスト (E2E_ADMIN_* / E2E_PARTNER_* 設定時のみ)
// ----------------------------------------------------------------

test.describe('/admin/login — 認証フロー (credentials 設定時のみ)', () => {
  test('正規 admin credential で /dashboard にリダイレクトされる', async ({ page }) => {
    test.skip(
      !ADMIN_EMAIL || !ADMIN_PASSWORD,
      'E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD 未設定のためスキップ',
    )

    await page.goto('/admin/login')
    await page.waitForLoadState('domcontentloaded')

    await page.getByTestId('admin-login-email').fill(ADMIN_EMAIL!)
    await page.getByTestId('admin-login-password').fill(ADMIN_PASSWORD!)
    await page.getByTestId('admin-login-submit').click()

    await page.waitForURL(/\/dashboard($|\?)/, { timeout: 15_000 })
    expect(page.url()).toContain('/dashboard')
    expect(page.url()).not.toContain('/admin/login')
  })

  test('一般ユーザー (partner) credential では admin としてログインできない', async ({ page }) => {
    test.skip(
      !PARTNER_EMAIL || !PARTNER_PASSWORD,
      'E2E_PARTNER_EMAIL / E2E_PARTNER_PASSWORD 未設定のためスキップ',
    )

    await page.goto('/admin/login')
    await page.waitForLoadState('domcontentloaded')

    await page.getByTestId('admin-login-email').fill(PARTNER_EMAIL!)
    await page.getByTestId('admin-login-password').fill(PARTNER_PASSWORD!)
    await page.getByTestId('admin-login-submit').click()

    // 期待動作: ログイン自体は成功するが role !== admin のため即ログアウト + エラー表示。
    // フォームは /admin/login に残ったまま。
    await expect(page.getByTestId('admin-login-error')).toBeVisible({ timeout: 15_000 })
    expect(page.url()).toContain('/admin/login')

    const errorText = await page.getByTestId('admin-login-error').textContent()
    expect(errorText ?? '').toMatch(/管理者専用|admin/i)
  })
})
