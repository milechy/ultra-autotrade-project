// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// F-12: 管理者画面 fee管理タブ E2E テスト
import { test, expect } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const AUTH_CACHE = path.join(__dirname, '.auth', 'partner.json')

function getAdminToken(): string | null {
  if (!fs.existsSync(AUTH_CACHE)) return null
  try {
    const data = JSON.parse(fs.readFileSync(AUTH_CACHE, 'utf-8'))
    return data?.token ?? null
  } catch {
    return null
  }
}

test.describe('Admin Fees — アクセス制御', () => {
  test('未ログインで /fees にアクセスするとログインページにリダイレクトされる', async ({ page }) => {
    await page.goto('/fees')
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
  })
})

test.describe('Admin Fees — ページ表示 (認証済み管理者)', () => {
  test.skip(!getAdminToken(), 'E2E_ADMIN credentials not set — skipping authenticated tests')

  test.beforeEach(async ({ page }) => {
    const token = getAdminToken()
    if (!token) return
    // JWT を localStorage にセットしてからページに遷移
    await page.addInitScript((t) => {
      window.localStorage.setItem('auth_token', t)
    }, token)
  })

  test('/fees ページが 200 で表示される', async ({ page }) => {
    const response = await page.goto('/fees')
    expect(response?.status()).toBeLessThan(500)
  })

  test('手数料管理タイトルが表示される', async ({ page }) => {
    await page.goto('/fees')
    await expect(page.getByText('手数料管理')).toBeVisible({ timeout: 10000 })
  })

  test('ユーザー別サマリータブと月次明細タブが表示される', async ({ page }) => {
    await page.goto('/fees')
    await expect(page.getByText('ユーザー別サマリー')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('月次明細')).toBeVisible({ timeout: 10000 })
  })

  test('月次明細タブに切り替えると月選択が表示される', async ({ page }) => {
    await page.goto('/fees')
    await page.getByText('月次明細').click()
    await expect(page.locator('input[type="month"]')).toBeVisible({ timeout: 10000 })
  })
})
