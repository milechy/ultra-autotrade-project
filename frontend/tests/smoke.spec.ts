// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test('トップページが表示される', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/.+/);
});

test('ログインページが表示される', async ({ page }) => {
  const response = await page.goto('/login');
  expect(response?.status()).toBe(200);
});

test('API ヘルスチェックが 200 を返す', async ({ request }) => {
  const response = await request.get(`${process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:8000'}/health`);
  expect(response.status()).toBe(200);
});
