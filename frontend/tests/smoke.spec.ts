import { test, expect } from '@playwright/test';

test('トップページが表示される', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/.+/);
});

test('ログインページが表示される', async ({ page }) => {
  const response = await page.goto('/auth/login');
  expect(response?.status()).toBe(200);
});

test('API ヘルスチェックが 200 を返す', async ({ request }) => {
  const response = await request.get('https://api.ultra-auto-trade.com/health');
  expect(response.status()).toBe(200);
});
