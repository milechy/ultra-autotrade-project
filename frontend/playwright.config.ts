// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { defineConfig, devices } from '@playwright/test'

const cfAccessHeaders: Record<string, string> =
  process.env.CF_ACCESS_CLIENT_ID && process.env.CF_ACCESS_CLIENT_SECRET
    ? {
        'CF-Access-Client-Id': process.env.CF_ACCESS_CLIENT_ID,
        'CF-Access-Client-Secret': process.env.CF_ACCESS_CLIENT_SECRET,
      }
    : {}

export default defineConfig({
  globalSetup: require.resolve('./e2e/global-setup'),
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : 3,
  // json reporter は scripts/launch_gate/L3_e2e.sh が
  // passed / failed / skipped 件数を読むために必要 (§7 skip-only 防止判定)
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
    ['json', { outputFile: 'playwright-results.json' }],
  ],
  use: {
    baseURL: process.env.STAGING_URL || 'https://app.ultra-auto-trade.com',
    locale: 'ja-JP',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    extraHTTPHeaders: cfAccessHeaders,
  },
  projects: [
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Desktop Chrome',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
