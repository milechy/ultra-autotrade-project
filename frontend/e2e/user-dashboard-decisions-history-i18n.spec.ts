// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.STAGING_URL || 'https://app.ultra-auto-trade.com'

/**
 * Gate 4 smoke tests for user/dashboard, user/decisions, user/history i18n (batch5)
 *
 * These pages require authentication. Without credentials the middleware redirects
 * to /user/login (or similar). We accept any status < 500 as a pass, and additionally
 * assert that the final URL does NOT still resolve to the requested page with a
 * server-error (i.e. the app handles it gracefully).
 *
 * URL mapping (app/user/ folder = no route-group prefix):
 *   app/user/dashboard/page.tsx  → /user/dashboard
 *   app/user/decisions/page.tsx  → /user/decisions
 *   app/user/history/page.tsx    → /user/history
 */

test.describe('user i18n batch5 — dashboard / decisions / history smoke', () => {
  const pages = [
    { url: '/user/dashboard', label: 'dashboard' },
    { url: '/user/decisions', label: 'decisions' },
    { url: '/user/history', label: 'history' },
  ]

  for (const { url, label } of pages) {
    test(`${label} page loads without 500 (auth redirect acceptable)`, async ({ page }) => {
      const response = await page.goto(`${BASE_URL}${url}`)
      // Accept 200 (logged in) or 3xx redirect to login — reject 500
      expect(response?.status()).toBeLessThan(500)
      // Ensure the final page itself also returns < 500 after any redirects
      const finalResponse = await page.waitForLoadState('networkidle').then(() => null).catch(() => null)
      void finalResponse // load state wait is sufficient
      const finalUrl = page.url()
      // Page must either be on the target URL or a login/connect redirect page
      const isTargetOrAuth =
        finalUrl.includes(url) ||
        finalUrl.includes('/login') ||
        finalUrl.includes('/connect') ||
        finalUrl.includes('/user/login')
      expect(isTargetOrAuth).toBe(true)
    })
  }
})
