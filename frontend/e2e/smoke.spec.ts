// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { test, expect } from '@playwright/test'

test.describe('Smoke Tests — Page Load', () => {
  test('トップページ（/）が200で読み込める', async ({ page }) => {
    const response = await page.goto('/')
    expect(response?.status()).toBe(200)
  })

  test('/connect ページが表示される（status < 500）', async ({ page }) => {
    const response = await page.goto('/connect')
    expect(response?.status()).toBeLessThan(500)
  })

  test('/terms ページが表示される（status < 500）', async ({ page }) => {
    const response = await page.goto('/terms')
    expect(response?.status()).toBeLessThan(500)
  })

  test('/risk-disclosure ページが表示される（status < 500）', async ({ page }) => {
    const response = await page.goto('/risk-disclosure')
    expect(response?.status()).toBeLessThan(500)
  })
})
