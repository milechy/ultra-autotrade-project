// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-06 取引履歴 (/history)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/history');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/history');
    expect(response?.status()).toBe(200);
  });

  test('ページ見出し「取引履歴」が表示される', async ({ page }) => {
    const heading = page.getByRole('heading', { name: '取引履歴' });
    await expect(heading).toBeVisible();
  });

  test('統計カード（総取引数/総利益/総手数料）が表示される', async ({ page }) => {
    // StatsCards コンポーネント: KPICard label
    await expect(page.getByText('総取引数')).toBeVisible();
    await expect(page.getByText('総利益')).toBeVisible();
    await expect(page.getByText('総手数料')).toBeVisible();
  });

  test('フィルターボタン群（ALL/SUPPLY/WITHDRAW等）が表示される', async ({ page }) => {
    // TransactionFilters: SUPPLY/WITHDRAW は操作種別フィルターにのみ存在
    // ALL は DateRangeFilter にも存在するため .first() で先頭を取得
    const allBtn = page.getByRole('button', { name: 'ALL' }).first();
    await expect(allBtn).toBeVisible();
    const supplyBtn = page.getByRole('button', { name: 'SUPPLY' });
    await expect(supplyBtn).toBeVisible();
    const withdrawBtn = page.getByRole('button', { name: 'WITHDRAW' });
    await expect(withdrawBtn).toBeVisible();
  });

  test('取引リストまたは「取引履歴がありません」メッセージが表示される', async ({ page }) => {
    // MOCK_TRANSACTIONS があるので取引リストが表示される
    const list = page.getByText(/SUPPLY|WITHDRAW|BORROW|REPAY|取引履歴がありません/).first();
    await expect(list).toBeVisible();
  });
});
