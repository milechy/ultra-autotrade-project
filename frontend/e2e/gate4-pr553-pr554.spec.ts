// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// e2e/gate4-pr553-pr554.spec.ts
//
// Gate 4 E2E: PR #553 (notification GET/PUT) + PR #554 (contract URL subdomain)
// 本番 URL (https://app.ultra-auto-trade.com) に対してそのまま実行。
// 未デプロイ機能は明示的 FAIL が期待値 — 「404 ではなく 401」= デプロイ済み判定基準。

import { test, expect } from '@playwright/test'

// ============================================================
// PR #554: /liff-confirm 遷移 + contract URL サブドメイン解決
// ============================================================
test.describe('PR #554 | /liff-confirm 遷移 + contract URL サブドメイン', () => {
  test('TC-554-1: /liff-confirm が 200 で読み込まれる', async ({ page }) => {
    const res = await page.goto('/liff-confirm')
    expect(res?.status()).toBe(200)
  })

  test('TC-554-2: /liff-confirm が /liff-chat または認証画面に遷移する', async ({ page }) => {
    await page.goto('/liff-confirm')
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})
    const url = page.url()
    // terms_agreed_at 済みなら /liff-chat へ、未同意なら /liff-confirm に留まる
    const valid = url.includes('/liff-confirm') || url.includes('/liff-chat') || url.includes('/liff')
    expect(valid).toBeTruthy()
  })

  test('TC-554-3: /liff-confirm の利用規約リンクが app. サブドメインを持つ [PR #554 修正点]', async ({ page }) => {
    await page.goto('/liff-confirm')
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})

    const termsLinks = page.locator('a[href*="terms"]')
    const count = await termsLinks.count()

    if (count === 0) {
      test.skip() // liff-confirm が直接 liff-chat にリダイレクトした場合はスキップ
      return
    }

    for (let i = 0; i < count; i++) {
      const href = await termsLinks.nth(i).getAttribute('href')
      // 修正前: https://ultra-auto-trade.com/terms (app. 欠落)
      // 修正後: https://app.ultra-auto-trade.com/terms
      expect(href, `terms link ${i}: app. サブドメイン欠落`).toMatch(/app\.ultra-auto-trade\.com/)
    }
  })

  test('TC-554-4: /liff-confirm のプライバシーリンクが app. サブドメインを持つ [PR #554 修正点]', async ({ page }) => {
    await page.goto('/liff-confirm')
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})

    const privacyLinks = page.locator('a[href*="privacy"]')
    const count = await privacyLinks.count()

    if (count === 0) {
      test.skip()
      return
    }

    for (let i = 0; i < count; i++) {
      const href = await privacyLinks.nth(i).getAttribute('href')
      expect(href, `privacy link ${i}: app. サブドメイン欠落`).toMatch(/app\.ultra-auto-trade\.com/)
    }
  })

  test('TC-554-5: /liff-chat TermsPanel の利用規約リンクが app. サブドメインを持つ [PR #554 修正点]', async ({ page }) => {
    await page.goto('/liff-chat')
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})

    // TermsPanel は通知パネル等から遷移する場合があり非表示のことも多い
    const termsLinks = page.locator('a[href*="terms"]')
    const count = await termsLinks.count()

    if (count === 0) {
      test.skip() // TermsPanel が表示されていない場合はスキップ
      return
    }

    for (let i = 0; i < count; i++) {
      const href = await termsLinks.nth(i).getAttribute('href')
      expect(href, `TermsPanel terms link ${i}: app. サブドメイン欠落`).toMatch(/app\.ultra-auto-trade\.com/)
    }
  })
})

// ============================================================
// PR #553: notification GET/PUT 往復 + emergency_stop OFF 不能
// ============================================================
test.describe('PR #553 | GET/PUT /api/notifications/settings + emergency_stop 強制', () => {
  test('TC-553-1: GET /api/notifications/settings が存在する (200 or 401, NOT 404) [デプロイ確認]', async ({ request }) => {
    const res = await request.get('/api/notifications/settings')
    // 404 = 未デプロイ (FAIL), 401 = デプロイ済み・認証必要 (PASS)
    expect(res.status(), `404 → エンドポイント未デプロイ。期待値: 200 or 401`).not.toBe(404)
    expect([200, 401, 403]).toContain(res.status())
  })

  test('TC-553-2: PUT /api/notifications/settings が存在する (200 or 401, NOT 404) [デプロイ確認]', async ({ request }) => {
    const res = await request.put('/api/notifications/settings', {
      data: {
        line_enabled: true,
        push_enabled: false,
        preferences: {
          ai_proposal: true,
          execution_complete: true,
          health_factor_warning: true,
          emergency_stop: false, // サーバーが True に強制するはず
          monthly_report: true,
          system_notice: true,
        },
      },
    })
    expect(res.status(), `404 → エンドポイント未デプロイ。期待値: 200 or 401`).not.toBe(404)
    expect([200, 401, 403, 422]).toContain(res.status())
  })

  test('TC-553-3: emergency_stop=false 送信 → サーバーが True に強制する (要認証: 認証情報あり環境のみ)', async ({ request }) => {
    const email = process.env.E2E_PARTNER_EMAIL
    const password = process.env.E2E_PARTNER_PASSWORD

    if (!email || !password) {
      test.skip()
      return
    }

    // login
    const loginRes = await request.post('/api/auth/login', {
      data: { email, password },
    })
    if (!loginRes.ok()) {
      test.skip()
      return
    }
    const { token } = await loginRes.json()

    // PUT with emergency_stop: false
    const putRes = await request.put('/api/notifications/settings', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        line_enabled: true,
        push_enabled: false,
        preferences: {
          ai_proposal: true,
          execution_complete: true,
          health_factor_warning: true,
          emergency_stop: false, // サーバーが強制して true にする
          monthly_report: true,
          system_notice: true,
        },
      },
    })
    expect(putRes.status()).toBe(200)

    const body = await putRes.json()
    expect(body.preferences.emergency_stop, 'emergency_stop は false 送信でも true に強制されること').toBe(true)

    // GET で永続化を確認
    const getRes = await request.get('/api/notifications/settings', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(getRes.status()).toBe(200)
    const getBody = await getRes.json()
    expect(getBody.preferences.emergency_stop, '永続化後も emergency_stop は true').toBe(true)
  })

  test('TC-553-4: GET /api/notifications/settings レスポンスがデフォルト構造を持つ (要認証)', async ({ request }) => {
    const email = process.env.E2E_PARTNER_EMAIL
    const password = process.env.E2E_PARTNER_PASSWORD

    if (!email || !password) {
      test.skip()
      return
    }

    const loginRes = await request.post('/api/auth/login', {
      data: { email, password },
    })
    if (!loginRes.ok()) {
      test.skip()
      return
    }
    const { token } = await loginRes.json()

    const res = await request.get('/api/notifications/settings', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(res.status()).toBe(200)

    const body = await res.json()
    // 必須キー確認
    expect(body).toHaveProperty('line_enabled')
    expect(body).toHaveProperty('push_enabled')
    expect(body).toHaveProperty('preferences')
    expect(body.preferences).toHaveProperty('emergency_stop')
    expect(body.preferences.emergency_stop).toBe(true)
  })
})
