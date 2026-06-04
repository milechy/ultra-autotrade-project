// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// viewer-rbac.spec.ts — VIEWER role 権限分離 E2E テスト
//
// 検証内容:
//   viewer ロール: 運用モード変更 / 緊急停止 / AI 承認 UI が非表示
//   admin ロール:  上記 UI が表示される
//
// 実行方法:
//   npx playwright test e2e/viewer-rbac.spec.ts
//   STAGING_URL=http://127.0.0.1:3000 npx playwright test e2e/viewer-rbac.spec.ts

import { test, expect, type Page } from '@playwright/test'

// ---- Mock user definitions ----

const VIEWER_MOCK_USER = {
  id: 98,
  email: 'viewer-e2e@ultra-autotrade.com',
  username: 'viewer-e2e',
  role: 'viewer',
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

const EDITOR_MOCK_USER = {
  id: 97,
  email: 'editor-e2e@ultra-autotrade.com',
  username: 'editor-e2e',
  role: 'editor',
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

const ADMIN_MOCK_USER = {
  id: 1,
  email: 'admin-e2e@ultra-autotrade.com',
  username: 'admin-e2e',
  role: 'admin',
  is_active: true,
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
  terms_accepted_at: null,
  terms_version: null,
  risk_mode: 'balanced',
  invited_by: null,
  tier: 'GENERAL',
  risk_mode_label: 'バランス',
}

// ---- Auth setup helpers ----

async function setupAuth(page: Page, mockUser: typeof VIEWER_MOCK_USER): Promise<void> {
  const expiresAt = Date.now() + 24 * 60 * 60 * 1000

  await page.addInitScript(
    (args: { tokenKey: string; expiresKey: string; t: string; e: number }) => {
      localStorage.setItem(args.tokenKey, args.t)
      localStorage.setItem(args.expiresKey, String(args.e))
    },
    {
      tokenKey: 'ultra_auth_token',
      expiresKey: 'ultra_auth_expires',
      t: `dummy-${mockUser.role}-token-for-e2e`,
      e: expiresAt,
    },
  )

  await page.route('**/auth/me', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockUser),
      })
    } else {
      await route.continue()
    }
  })

  // Mock common API endpoints to prevent network errors
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

  await page.route('**/api/automation/status', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          is_trading_paused: false,
          emergency_reason: null,
          last_updated: new Date().toISOString(),
        }),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/auth/risk-mode', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ mode: 'conservative' }),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/auth/risk-modes', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          modes: [{ mode: 'conservative', allowed_in_phase_1: true }],
        }),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/api/proposals/pending', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/api/proposals/history**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      })
    } else {
      await route.continue()
    }
  })
}

// ---- viewer ロールのテスト ----

test.describe('viewer ロール — 操作系 UI が非表示', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page, VIEWER_MOCK_USER)
  })

  test('設定ページ: 運用モードセクションが非表示', async ({ page }) => {
    await page.goto('/user/settings')
    await page.waitForLoadState('networkidle')

    const operationModeSection = page.locator('[data-testid="operation-mode-section"]')
    await expect(operationModeSection).toHaveCount(0)
  })

  test('設定ページ: リスク設定セクションが非表示', async ({ page }) => {
    await page.goto('/user/settings')
    await page.waitForLoadState('networkidle')

    const riskSettingsSection = page.locator('[data-testid="risk-settings-section"]')
    await expect(riskSettingsSection).toHaveCount(0)
  })

  test('ダッシュボード: 緊急停止フロートボタンが非表示', async ({ page }) => {
    await page.goto('/user/dashboard')
    await page.waitForLoadState('networkidle')

    const emergencyStop = page.locator('[data-testid="emergency-stop-float"]')
    await expect(emergencyStop).toHaveCount(0)
  })

  test('承認ページ: viewer はダッシュボードにリダイレクトされる', async ({ page }) => {
    await page.goto('/user/approve')
    // viewer は !isPartner のため /user/dashboard にリダイレクト
    await page.waitForURL(/\/(user\/dashboard|login)/, { timeout: 5000 })
    const currentUrl = page.url()
    expect(currentUrl).not.toContain('/user/approve')
  })

  test('BottomNav: 「設定」タブが非表示', async ({ page }) => {
    await page.goto('/user/dashboard')
    await page.waitForLoadState('networkidle')

    const settingsLink = page.locator('nav a[href="/user/settings"]')
    await expect(settingsLink).toHaveCount(0)
  })

  test('BottomNav: 「承認」タブが非表示', async ({ page }) => {
    await page.goto('/user/dashboard')
    await page.waitForLoadState('networkidle')

    const approveLink = page.locator('nav a[href="/user/approve"]')
    await expect(approveLink).toHaveCount(0)
  })
})

// ---- editor ロールのテスト ----

test.describe('editor ロール — 操作系 UI が非表示', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page, EDITOR_MOCK_USER)
  })

  test('設定ページ: 運用モードセクションが非表示', async ({ page }) => {
    await page.goto('/user/settings')
    await page.waitForLoadState('networkidle')

    const operationModeSection = page.locator('[data-testid="operation-mode-section"]')
    await expect(operationModeSection).toHaveCount(0)
  })

  test('ダッシュボード: 緊急停止フロートボタンが非表示', async ({ page }) => {
    await page.goto('/user/dashboard')
    await page.waitForLoadState('networkidle')

    const emergencyStop = page.locator('[data-testid="emergency-stop-float"]')
    await expect(emergencyStop).toHaveCount(0)
  })
})

// ---- admin ロールのテスト ----

test.describe('admin ロール — 操作系 UI が表示される', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page, ADMIN_MOCK_USER)
  })

  test('設定ページ: 運用モードセクションが表示される', async ({ page }) => {
    await page.goto('/user/settings')
    await page.waitForLoadState('networkidle')

    const operationModeSection = page.locator('[data-testid="operation-mode-section"]')
    await expect(operationModeSection).toBeVisible()
  })

  test('設定ページ: リスク設定セクションが表示される', async ({ page }) => {
    await page.goto('/user/settings')
    await page.waitForLoadState('networkidle')

    const riskSettingsSection = page.locator('[data-testid="risk-settings-section"]')
    await expect(riskSettingsSection).toBeVisible()
  })

  test('ダッシュボード: 緊急停止フロートボタンが表示される', async ({ page }) => {
    await page.goto('/user/dashboard')
    await page.waitForLoadState('networkidle')

    const emergencyStop = page.locator('[data-testid="emergency-stop-float"]')
    await expect(emergencyStop).toBeVisible()
  })

  test('承認ページ: admin はリダイレクトされない', async ({ page }) => {
    await page.goto('/user/approve')
    await page.waitForLoadState('networkidle')

    // admin は /user/approve に留まる (リダイレクトされない)
    expect(page.url()).toContain('/user/approve')
  })

  test('BottomNav: 「設定」タブが表示される', async ({ page }) => {
    await page.goto('/user/dashboard')
    await page.waitForLoadState('networkidle')

    const settingsLink = page.locator('nav a[href="/user/settings"]')
    await expect(settingsLink).toBeVisible()
  })
})
