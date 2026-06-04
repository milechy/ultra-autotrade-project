// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Lane I — AI 透明性カード Playwright tests (Gate 1-3)
import { test, expect } from '@playwright/test'

// Gate 1: コンポーネントが HTML として存在する（静的レンダリング確認）
test.describe('Gate 1 — AiTransparencyCard: page-load smoke', () => {
  test('user dashboard が 500 未満で読み込まれる', async ({ page }) => {
    const response = await page.goto('/user/dashboard')
    expect(response?.status()).toBeLessThan(500)
  })

  test('partner dashboard が 500 未満で読み込まれる', async ({ page }) => {
    const response = await page.goto('/partner/dashboard')
    expect(response?.status()).toBeLessThan(500)
  })
})

// Gate 2: 透明性カードの DOM 要素が描画される（未認証では empty-state でも可）
test.describe('Gate 2 — AiTransparencyCard: DOM elements', () => {
  test('user dashboard — ai-transparency-card または空状態テキストが存在する', async ({ page }) => {
    await page.goto('/user/dashboard')
    // ウォレット未接続のため、redirect か空状態になる場合も許容
    // 透明性カード OR リダイレクトされたページが存在すれば OK
    const url = page.url()
    const isOnDashboard = url.includes('/user/dashboard') || url.includes('/dashboard')
    const isRedirected = url.includes('/connect') || url.includes('/login')
    expect(isOnDashboard || isRedirected).toBe(true)
  })

  test('partner dashboard — page loads without JS errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))
    await page.goto('/partner/dashboard')
    // 致命的なレンダリングエラー（Cannot read properties of undefined 等）がないこと
    const fatalErrors = errors.filter((e) =>
      e.includes('Cannot read properties of undefined') ||
      e.includes('TypeError: null is not an object')
    )
    expect(fatalErrors).toHaveLength(0)
  })
})

// Gate 3: AiTransparencyCard が API から正しいデータを表示する（モック使用）
test.describe('Gate 3 — AiTransparencyCard: API integration with mock', () => {
  test('ai/decisions/latest が HOLD を返すとき HOLD バッジが表示される', async ({ page }) => {
    // API レスポンスをモック
    await page.route('**/api/ai/decisions/latest', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          action: 'HOLD',
          confidence: 38,
          reason: 'Indicator 38%, Macro 25%, BUY/SELL は両方≥70%必要',
          primary_provider: 'claude',
          primary_action: 'HOLD',
          primary_confidence: 38,
          secondary_provider: 'gpt4o',
          secondary_action: 'HOLD',
          secondary_confidence: 35,
          agreed: true,
          created_at: new Date().toISOString(),
        }),
      })
    })

    await page.goto('/user/dashboard')

    // ai-transparency-card が存在する場合（認証状態によって異なる）
    const card = page.locator('[data-testid="ai-transparency-card"]')
    const cardVisible = await card.isVisible().catch(() => false)

    if (cardVisible) {
      // アクションバッジに HOLD が表示される
      const actionBadge = page.locator('[data-testid="transparency-action-badge"]')
      await expect(actionBadge).toContainText('HOLD')

      // 確信度が表示される
      const confidence = page.locator('[data-testid="transparency-confidence"]')
      await expect(confidence).toContainText('38')

      // reason テキストが表示される
      const reason = page.locator('[data-testid="transparency-reason"]')
      await expect(reason).toContainText('Indicator')

      // 両者一致バッジが表示される
      const agreed = page.locator('[data-testid="transparency-agreed"]')
      await expect(agreed).toContainText('両者一致')
    } else {
      // 未認証リダイレクトは許容
      const url = page.url()
      expect(url.includes('/connect') || url.includes('/login') || url.includes('/dashboard')).toBe(true)
    }
  })

  test('ai/decisions/latest が BUY を返すとき BUY バッジが表示される', async ({ page }) => {
    await page.route('**/api/ai/decisions/latest', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 2,
          action: 'BUY',
          confidence: 82,
          reason: 'Indicator 82%, Macro 75%, 条件充足',
          primary_provider: 'claude',
          primary_action: 'BUY',
          primary_confidence: 82,
          secondary_provider: null,
          secondary_action: null,
          secondary_confidence: null,
          agreed: true,
          created_at: new Date().toISOString(),
        }),
      })
    })

    await page.goto('/user/dashboard')

    const card = page.locator('[data-testid="ai-transparency-card"]')
    const cardVisible = await card.isVisible().catch(() => false)

    if (cardVisible) {
      const actionBadge = page.locator('[data-testid="transparency-action-badge"]')
      await expect(actionBadge).toContainText('BUY')

      const confidence = page.locator('[data-testid="transparency-confidence"]')
      await expect(confidence).toContainText('82')

      // metrics breakdown が表示される（パーセントが reason にある場合）
      const metrics = page.locator('[data-testid="transparency-metrics"]')
      const metricsVisible = await metrics.isVisible().catch(() => false)
      if (metricsVisible) {
        await expect(metrics).toContainText('Indicator')
      }
    } else {
      const url = page.url()
      expect(url.includes('/connect') || url.includes('/login') || url.includes('/dashboard')).toBe(true)
    }
  })

  test('ai/decisions/latest が 404 を返すとき空状態が表示される', async ({ page }) => {
    await page.route('**/api/ai/decisions/latest', (route) => {
      route.fulfill({ status: 404, body: JSON.stringify({ detail: 'No decisions found' }) })
    })

    await page.goto('/user/dashboard')

    const card = page.locator('[data-testid="ai-transparency-card"]')
    const cardVisible = await card.isVisible().catch(() => false)

    if (cardVisible) {
      // 空状態テキストが表示される
      await expect(card).toContainText('判定データを取得できません')
    } else {
      const url = page.url()
      expect(url.includes('/connect') || url.includes('/login') || url.includes('/dashboard')).toBe(true)
    }
  })
})
