// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// 回帰テスト: ネスト NextIntlClientProvider の messages 部分指定による
// MISSING_MESSAGE → i18n 生キー表示バグ (2026-06-25)。
//
// 背景: UserProviders / AdminProviders / PartnerProviders の Guard が
// `messages={{ ProvidersX }}` のように部分 messages で子孫を包むと、next-intl の
// ネスト provider は messages をマージせず置換するため、UserHeader / AppShell /
// TermsModal 等の namespace が解決できず生キー (例 "UserHeader.viewerNav.dashboard")
// が表示される。本テストは公開ページ /connect で生キー非表示を保証する。

import { test, expect } from '@playwright/test'

test.describe('i18n provider 回帰 — ネスト provider の messages 欠落検出', () => {
  test('/connect に i18n 生キーが表示されない', async ({ page }) => {
    const missingMessageErrors: string[] = []
    page.on('console', (m) => {
      if (m.type() === 'error' && m.text().includes('MISSING_MESSAGE')) {
        missingMessageErrors.push(m.text().split('\n')[0])
      }
    })

    await page.goto('/connect')
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1500)

    const bodyText = await page.locator('body').innerText()
    // "Namespace.path.to.key" 形式の未解決 i18n キー (UserHeader.viewerNav.dashboard 等)
    const rawKeys = bodyText.match(/[A-Z][a-zA-Z]+\.[a-zA-Z]+\.[a-zA-Z.]+/g) || []

    expect(
      rawKeys,
      `i18n 生キーが描画されています (ネスト provider の messages 欠落): ${JSON.stringify(rawKeys.slice(0, 8))}`,
    ).toHaveLength(0)
    expect(
      missingMessageErrors,
      `MISSING_MESSAGE エラー: ${JSON.stringify(missingMessageErrors.slice(0, 8))}`,
    ).toHaveLength(0)
  })
})
