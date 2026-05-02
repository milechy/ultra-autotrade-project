// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-01 ランディングページ (/)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/');
    expect(response?.status()).toBe(200);
  });

  test('ヒーローセクションのキャッチコピーが表示される', async ({ page }) => {
    const hero = page.locator('h1').filter({ hasText: /AIが導く|Ultra AutoTrade/ }).first();
    await expect(hero).toBeVisible();
  });

  test('CTAボタン「ウォレットで始める」が表示される', async ({ page }) => {
    const cta = page.getByRole('link', { name: 'ウォレットで始める' }).first();
    await expect(cta).toBeVisible();
  });

  test('CTAボタンクリックで /connect に遷移する', async ({ page }) => {
    const cta = page.getByRole('link', { name: 'ウォレットで始める' }).first();
    await cta.click();
    await page.waitForURL('**/connect');
    expect(page.url()).toContain('/connect');
  });

  test('FAQセクションが存在する（Accordionの存在確認）', async ({ page }) => {
    const faqHeading = page.getByText('よくある質問');
    await expect(faqHeading).toBeVisible();
    const accordion = page.locator('[data-radix-collection-item], [data-state]').first();
    await expect(accordion).toBeVisible();
  });

  test('リスク説明セクションが存在する', async ({ page }) => {
    const riskSection = page.getByText('リスク免責事項');
    await expect(riskSection).toBeVisible();
  });

  test('モバイルビューポートでも崩れない（スクリーンショット取得）', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    const hero = page.locator('h1').filter({ hasText: /AIが導く|Ultra AutoTrade/ }).first();
    await expect(hero).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/landing-mobile.png', fullPage: false });
  });
});
