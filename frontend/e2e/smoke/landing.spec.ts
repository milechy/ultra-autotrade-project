// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

// U-01: ルートページ (/) は未認証ユーザーを /login にリダイレクトする。
// 旧ランディングページコンテンツは hotfix/unauth-redirect-to-login で削除済み。
test.describe('U-01 ルートページ (/) リダイレクト', () => {
  test('ページが200で読み込まれる（クライアントサイドリダイレクト前のHTML）', async ({ page }) => {
    const response = await page.goto('/');
    expect(response?.status()).toBe(200);
  });

  test('未認証で / にアクセスすると /login にリダイレクトされる', async ({ page }) => {
    await page.goto('/');
    await page.waitForURL('**/login', { timeout: 8000 });
    expect(page.url()).toContain('/login');
  });

  test('モバイル（375px）で / にアクセスすると /login にリダイレクトされる', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    await page.waitForURL('**/login', { timeout: 8000 });
    await page.screenshot({ path: 'e2e/screenshots/login-mobile.png', fullPage: false });
    expect(page.url()).toContain('/login');
  });
});
