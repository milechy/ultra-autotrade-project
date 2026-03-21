// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('レスポンシブテスト', () => {
  test('モバイル（375px）: ボトムナビ表示', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/user/dashboard');
    // BottomNav: md:hidden → 375px では表示
    const nav = page.locator('nav').filter({ hasText: 'ダッシュボード' });
    await expect(nav).toBeVisible();
  });

  test('モバイル（375px）: ページが読み込まれる', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    const response = await page.goto('/user/dashboard');
    expect(response?.status()).toBe(200);
    await page.screenshot({ path: 'e2e/screenshots/dashboard-375.png' });
  });

  test('タブレット（768px）: ページが読み込まれる', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    const response = await page.goto('/user/dashboard');
    expect(response?.status()).toBe(200);
    await page.screenshot({ path: 'e2e/screenshots/dashboard-768.png' });
  });

  test('デスクトップ（1280px）: ページが読み込まれる', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const response = await page.goto('/user/dashboard');
    expect(response?.status()).toBe(200);
    await page.screenshot({ path: 'e2e/screenshots/dashboard-1280.png' });
  });

  test('デスクトップ（1280px）: ボトムナビが非表示', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/user/dashboard');
    // BottomNav: md:hidden → 1280px では非表示
    const nav = page.locator('nav').filter({ hasText: 'ダッシュボード' });
    await expect(nav).toBeHidden();
  });

  test('ランディングページ: モバイル（375px）でヒーローが表示される', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    const hero = page.locator('h1').filter({ hasText: 'AIが導く' });
    await expect(hero).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/landing-375.png' });
  });
});
