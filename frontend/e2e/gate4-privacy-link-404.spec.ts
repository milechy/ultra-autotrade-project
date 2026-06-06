// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// e2e/gate4-privacy-link-404.spec.ts
//
// Gate 4 E2E: プライバシーポリシーリンクの 404 回帰ガード
// (Asana 1215360586206558 オンボーディング / 1215466861197934 AppInfoCard)
//
// 背景: 実ルートは /privacy-policy のみ (frontend/app/(user)/privacy-policy)。
//       /privacy は存在せず 404。liff-confirm と AppInfoCard が旧 /privacy を
//       指していたため、法的同意画面で PP リンクが切れていた。
//       既存 gate4-pr553-pr554 の TC-554-4 は app. サブドメインの有無のみ検証し、
//       パス (/privacy vs /privacy-policy) を見ていなかったため 404 を見逃した。
//       本 spec はリンク先パスと実ルートの到達性を assert して再発を防ぐ。
//
// 本番 URL (https://app.ultra-auto-trade.com) に対してそのまま実行。

import { test, expect } from '@playwright/test'

test.describe('Gate4 | privacy-policy link 404 回帰ガード', () => {
  test('TC-PP-1: /privacy-policy が 200 で存在する (実ルート)', async ({ request }) => {
    const res = await request.get('/privacy-policy')
    expect(res.status(), '/privacy-policy は実ルート。404 なら設置漏れ').toBe(200)
  })

  test('TC-PP-2: /terms が 200 で存在する (実ルート)', async ({ request }) => {
    const res = await request.get('/terms')
    expect(res.status(), '/terms は実ルート。404 なら設置漏れ').toBe(200)
  })

  test('TC-PP-3: /privacy (旧パス) は実ルートではない (404 を文書化)', async ({ request }) => {
    // /privacy は存在しない。これを参照すると 404 になる = 修正の根拠。
    const res = await request.get('/privacy')
    expect(res.status(), '/privacy は存在しないパス。200 を返すなら本 spec の前提が変わったので見直す').toBe(404)
  })

  test('TC-PP-4: /liff-confirm のプライバシーリンクが /privacy-policy を指す (旧 /privacy ではない)', async ({ page }) => {
    await page.goto('/liff-confirm')
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})

    const privacyLinks = page.locator('a[href*="privacy"]')
    const count = await privacyLinks.count()

    if (count === 0) {
      test.skip() // 同意済みユーザーで liff-chat に即リダイレクトした場合
      return
    }

    for (let i = 0; i < count; i++) {
      const href = await privacyLinks.nth(i).getAttribute('href')
      // app. サブドメイン + /privacy-policy パス (旧 .../privacy は 404)
      expect(href, `privacy link ${i}: app. サブドメイン欠落`).toMatch(/app\.ultra-auto-trade\.com/)
      expect(href, `privacy link ${i}: 旧 /privacy (404) を指している。/privacy-policy に修正要`).toMatch(
        /\/privacy-policy(\b|$|\/)/
      )
    }
  })

  test('TC-PP-5: /liff-confirm の利用規約リンクが /terms を指す', async ({ page }) => {
    await page.goto('/liff-confirm')
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})

    const termsLinks = page.locator('a[href*="/terms"]')
    const count = await termsLinks.count()

    if (count === 0) {
      test.skip()
      return
    }

    for (let i = 0; i < count; i++) {
      const href = await termsLinks.nth(i).getAttribute('href')
      expect(href, `terms link ${i}: app. サブドメイン欠落`).toMatch(/app\.ultra-auto-trade\.com/)
      expect(href, `terms link ${i}: /terms を指していない`).toMatch(/\/terms(\b|$|\/)/)
    }
  })
})
