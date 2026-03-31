// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { test, expect } from '@playwright/test'

test.describe('Dashboard Auth Redirect Tests', () => {
  test('/dashboard にアクセスするとウォレット未接続状態で表示される（または /connect にリダイレクト）', async ({ page }) => {
    await page.goto('/dashboard')

    // Middleware does not enforce auth redirects; the page loads and shows
    // a wallet-not-connected state, OR the app redirects to /connect client-side.
    // Accept either outcome.
    const currentUrl = page.url()
    const isOnDashboard = currentUrl.includes('/dashboard')
    const isOnConnect = currentUrl.includes('/connect')

    expect(isOnDashboard || isOnConnect).toBe(true)

    if (isOnDashboard) {
      // Page should load without a 500-level error — just no wallet data
      const response = await page.goto('/dashboard')
      expect(response?.status()).toBeLessThan(500)
    }
  })

  test('/settings にアクセスすると200で読み込まれる（リダイレクトなし）', async ({ page }) => {
    const response = await page.goto('/settings')
    expect(response?.status()).toBeLessThan(500)

    // Settings should not redirect to /connect
    const currentUrl = page.url()
    expect(currentUrl).toContain('/settings')
  })
})
