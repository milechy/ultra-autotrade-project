// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  globalSetup: require.resolve('./e2e/global-setup'),
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : 3,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: process.env.STAGING_URL || 'https://app.ultra-auto-trade.com',
    locale: 'ja-JP',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
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
